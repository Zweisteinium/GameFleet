"""Creating a game server: write <servers_dir>/<folder>/<slug>/docker-compose.yml, .env and data/, pull the image,
`docker compose create`, link the container as a GameFleet server, then start it and wait until it is ready.

The compose file stays the source of truth, so the server can be edited by hand like any other compose project.
The backend writes it through the servers folder, which is mounted at the same path (settings_service), and runs
the docker compose CLI against the host daemon through the socket.
"""
import asyncio
import logging
import os
import time
import uuid
from typing import Optional

import aiohttp
import docker.errors

from gamefleet_backend.db.models.host_settings import HostSettingsBase
from gamefleet_backend.db.session import async_session
from gamefleet_backend.models.template import CreateJob, CreatePreview, CreateRequest, PortHolder, Template
from gamefleet_backend.services.docker_discovery_service import DockerDiscoveryService
from gamefleet_backend.services.docker_service import DockerUnavailable, docker_service, map_container
from gamefleet_backend.services.game_server_service import GameServerService
from gamefleet_backend.services.settings_service import servers_dir_problem
from gamefleet_backend.services.template_service import Rendered, TemplateError, get_template, render

log = logging.getLogger(__name__)

WAIT_TIMEOUT = 30 * 60  # seconds a first start may take (modpacks download hundreds of mods)
SETTLE_TIME = 20  # seconds a container without a healthcheck has to keep running to count as started
MINECRAFT_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"


class CreateError(Exception):
    """The creation failed; the message is shown to the user."""


async def port_holders(rendered: Rendered, linked: dict) -> list[PortHolder]:
    """Containers (running or not) that publish a host port the new server wants."""
    wanted = {(host, protocol) for host, _, protocol in rendered.ports}
    holders = []
    for raw in await docker_service.list_raw():
        raw = await docker_service.complete(raw)
        held = sorted({f"{b['PublicPort']}/{b.get('Type', 'tcp')}" for b in raw.get("Ports") or []
                       if (b.get("PublicPort"), b.get("Type", "tcp")) in wanted})
        if held:
            name = map_container(raw).name
            server = linked.get(name)
            holders.append(PortHolder(container_name=name, server_id=getattr(server, "id", None),
                                      server_name=getattr(server, "name", None),
                                      running=raw.get("State") == "running", ports=held))
    return holders


async def compose(rendered: Rendered, *args: str) -> str:
    process = await asyncio.create_subprocess_exec(
        "docker", "compose", "--project-directory", rendered.folder, "-p", rendered.project, *args,
        cwd=rendered.folder, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    output, _ = await process.communicate()
    text = output.decode("utf-8", errors="replace").strip()
    if process.returncode:
        raise CreateError(f"docker compose {args[0]} failed: {text.splitlines()[-1] if text else process.returncode}")
    return text


def write_files(rendered: Rendered, settings: HostSettingsBase) -> None:
    os.makedirs(os.path.dirname(rendered.folder), mode=0o755, exist_ok=True)
    os.mkdir(rendered.folder, 0o755)  # fails if it exists: never write into somebody's folder
    data = os.path.join(rendered.folder, "data")
    os.mkdir(data, 0o755)
    paths = [rendered.folder, data]
    for name, text, mode in (("docker-compose.yml", rendered.compose, 0o644), (".env", rendered.env_file, 0o600)):
        path = os.path.join(rendered.folder, name)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(fd, "w") as file:
            file.write(text)
        paths.append(path)
    if os.geteuid() == 0:  # in the container; a native development run writes as its own user
        for path in paths:
            os.chown(path, settings.owner_uid, settings.owner_gid)


class CreateService:
    def __init__(self) -> None:
        self.jobs: dict[str, CreateJob] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._versions: Optional[tuple[float, list[str]]] = None

    async def preview(self, request: CreateRequest, settings: HostSettingsBase,
                      service: GameServerService) -> tuple[CreatePreview, Optional[Rendered], Template]:
        """What the request creates, and every reason it cannot be created right now."""
        template = get_template(request.template)
        problems: list[str] = []
        rendered = None
        try:
            rendered = render(template, request, settings)
        except TemplateError as exc:
            problems.append(str(exc))
        if problem := await servers_dir_problem(settings):
            problems.append(problem)
        holders: list[PortHolder] = []
        if rendered:
            if os.path.lexists(rendered.folder):
                problems.append(f"{rendered.folder} exists already. Choose another folder name.")
            try:
                if await docker_service.get_raw(rendered.container_name):
                    problems.append(f"A container named {rendered.container_name} exists already.")
                linked = {s.container_name: s for s in await service.get_all_servers() if s.source == "docker"}
                holders = await port_holders(rendered, linked)
            except (DockerUnavailable, docker.errors.DockerException, OSError) as exc:
                problems.append(f"Docker is not available: {exc}")
        preview = CreatePreview(
            folder=rendered.folder if rendered else "", project=rendered.project if rendered else "",
            container_name=rendered.container_name if rendered else "", compose=rendered.compose if rendered else "",
            secrets=rendered.secrets if rendered else [],
            ports=[f"{h}/{p}" for h, _, p in rendered.ports] if rendered else [], holders=holders, problems=problems,
        )
        return preview, rendered, template

    def start(self, request: CreateRequest, template: Template, rendered: Rendered, settings: HostSettingsBase) -> CreateJob:
        job = CreateJob(id=uuid.uuid4().hex, name=request.name, folder=rendered.folder, phase="writing",
                        started_at=time.time(), ready_hint=template.ready_hint)
        self.jobs[job.id] = job

        async def guarded():
            try:
                await self._run(job, request, template, rendered, settings)
                job.phase = "done"
            except CreateError as exc:
                job.phase, job.error = "failed", str(exc)
            except Exception as exc:
                log.exception("Creating %s failed", rendered.folder)
                job.phase, job.error = "failed", f"{type(exc).__name__}: {exc}"
            finally:
                job.progress = None
                job.finished_at = time.time()
        self._tasks[job.id] = asyncio.create_task(guarded())
        return job

    async def _run(self, job: CreateJob, request: CreateRequest, template: Template, rendered: Rendered,
                   settings: HostSettingsBase) -> None:
        try:
            await asyncio.to_thread(write_files, rendered, settings)
        except OSError as exc:
            raise CreateError(f"Could not write {rendered.folder}: {exc}")

        job.phase, job.progress = "pulling", 0.0
        try:
            await docker_service.pull(rendered.image, lambda fraction: setattr(job, "progress", fraction))
        except docker.errors.APIError as exc:
            raise CreateError(f"Could not pull {rendered.image}: {exc.explanation or exc}. The files are in "
                              f"{rendered.folder}; delete the folder to try again with the same name.")
        job.progress = None

        job.phase = "creating"
        await compose(rendered, "create", "--no-recreate")
        raw = await docker_service.get_raw(rendered.container_name)
        if raw is None:
            raise CreateError(f"docker compose did not create {rendered.container_name}")
        async with async_session() as session:
            server = await DockerDiscoveryService(session).import_container(raw, game=template.game, name=request.name)
            server.template, server.compose_file = template.id, os.path.join(rendered.folder, "docker-compose.yml")
            server.compose_hash, server.is_public = rendered.compose_hash, request.is_public
            session.add(server)
            await session.commit()
            job.server_id = server.id
            linked = {s.container_name: s for s in await GameServerService(session).get_all_servers() if s.source == "docker"}
        if not request.start:
            return

        job.phase = "starting"
        held = await docker_service.port_conflicts(rendered.container_name)
        if held:
            foreign = [name for name in held if name not in linked]
            names = ", ".join(getattr(linked.get(n), "name", None) or n for n in held)
            if not request.stop_conflicting or foreign:
                job.warning = f"Created but not started: {names} uses the port. Start it from the server page."
                return
            for name in held:
                await docker_service.power(name, "stop")
                docker_service.forget(name)
        await docker_service.power(rendered.container_name, "start")
        docker_service.forget(rendered.container_name)
        job.started = True

        job.phase = "waiting"
        started, deadline = time.monotonic(), time.monotonic() + WAIT_TIMEOUT
        while True:
            state = (await docker_service.inspect(rendered.container_name)).get("State") or {}
            job.log = await docker_service.logs(rendered.container_name, 30)
            job.health = (state.get("Health") or {}).get("Status")
            if state.get("Restarting") or not state.get("Running"):
                raise CreateError(f"The server stopped during its first start (exit code {state.get('ExitCode')}). "
                                  "The log below shows why.")
            if job.health == "healthy" or (job.health is None and time.monotonic() - started >= SETTLE_TIME):
                return
            if time.monotonic() > deadline:
                job.warning = "Not ready after 30 minutes; it keeps starting in the background."
                return
            await asyncio.sleep(2)

    async def minecraft_versions(self) -> list[str]:
        """Minecraft releases, newest first (cached for an hour)."""
        if self._versions and time.monotonic() - self._versions[0] < 3600:
            return self._versions[1]
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(MINECRAFT_MANIFEST) as response:
                    response.raise_for_status()
                    manifest = await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            log.warning("Minecraft version list unavailable: %s", exc)
            return self._versions[1] if self._versions else []
        versions = [v["id"] for v in manifest.get("versions", []) if v.get("type") == "release"]
        self._versions = (time.monotonic(), versions)
        return versions


create_service = CreateService()
