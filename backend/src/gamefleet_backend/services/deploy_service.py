"""Deploying a new game server as a Docker container on this host.

A template per game names the image, the ports, the environment variables worth asking for and where the
image keeps its data. A deploy pulls the image, creates the container with bind mounts below SERVERS_ROOT
(`<root>/<game>/<slug>`), writes a docker-compose.yml that reproduces it next to the data so the server can
be managed by hand later, starts it and imports it as a GameFleet server. Everything after validation runs
as a background job that the UI polls.

SERVERS_ROOT is a path on the Docker host: Docker creates the bind-mount directories itself, and files are
written through a throwaway helper container that mounts the directory, so the backend never needs it.
"""
import asyncio
import io
import logging
import os
import posixpath
import re
import secrets
import tarfile
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import docker.errors
from sqlalchemy.ext.asyncio import AsyncSession

from gamefleet_backend.db.session import async_session
from gamefleet_backend.models.deploy import (
    DeployCheckResult, DeployField, DeployJob, DeployPort, DeployRequest, DeployTemplate, FieldValue, PortIssue,
)
from gamefleet_backend.models.game_server_type import GAME_CATALOG, GameServerType
from gamefleet_backend.services.docker_service import HELPER_PREFIX, docker_service

log = logging.getLogger(__name__)

SERVERS_ROOT = os.getenv("SERVERS_ROOT", "/opt/gamefleet/servers").rstrip("/") or "/"
ROOT_MOUNT = "/gamefleet-root"  # where the helper sees the server's directory
JOB_KEEP = 50  # finished jobs kept in memory


class DeployError(Exception):
    """A problem the user can act on; the message is shown as is."""


@dataclass(frozen=True)
class Template:
    game: GameServerType
    image: str
    description: str
    memory_hint: str
    fields: tuple[DeployField, ...]
    ports: tuple[DeployPort, ...]
    volumes: tuple[tuple[str, str], ...]  # (subdirectory, path inside the container); the first is the data dir
    stop_timeout: int
    fixed_env: dict[str, str] = field(default_factory=dict)
    owner: Optional[str] = None  # uid:gid the image runs as, applied to the data directory
    rcon_env: Optional[str] = None  # variable whose generated value is the RCON password


def _f(key: str, label: str, type: str, default: FieldValue = None, required: bool = False,
       options: tuple[str, ...] = (), description: str = "", group: str = "") -> DeployField:
    return DeployField(key=key, label=label, type=type, default=default, required=required,
                       options=list(options), description=description, group=group)


TEMPLATES: dict[str, Template] = {
    "minecraft": Template(
        GameServerType.minecraft, "itzg/minecraft-server:latest",
        "Java edition through itzg/minecraft-server: vanilla, Paper, Fabric, Forge, NeoForge or a modpack from "
        "Modrinth or CurseForge. The server jar is downloaded on the first start.",
        "2 GB RAM for vanilla, 6 GB and more for modpacks",
        (
            _f("TYPE", "Server type", "enum", "PAPER", options=("VANILLA", "PAPER", "FABRIC", "FORGE", "NEOFORGE", "MODRINTH", "AUTO_CURSEFORGE"),
               description="MODRINTH and AUTO_CURSEFORGE install the modpack named below.", group="Software"),
            _f("VERSION", "Minecraft version", "str", "LATEST", description="LATEST, SNAPSHOT or a version such as 1.21.4.", group="Software"),
            _f("MODRINTH_MODPACK", "Modrinth modpack", "str", description="Project slug or URL, for TYPE=MODRINTH.", group="Software"),
            _f("CF_SLUG", "CurseForge modpack", "str", description="Project slug, for TYPE=AUTO_CURSEFORGE (needs CF_API_KEY in the compose file).", group="Software"),
            _f("MEMORY", "Memory", "str", "4G", description="Java heap, e.g. 2G or 8G.", group="Resources"),
            _f("MOTD", "Message of the day", "str", "A Minecraft Server", group="Game"),
            _f("MAX_PLAYERS", "Max players", "int", 20, group="Game"),
            _f("DIFFICULTY", "Difficulty", "enum", "normal", options=("peaceful", "easy", "normal", "hard"), group="Game"),
            _f("MODE", "Game mode", "enum", "survival", options=("survival", "creative", "adventure", "spectator"), group="Game"),
            _f("ONLINE_MODE", "Online mode", "bool", True, description="Verify players with Mojang.", group="Game"),
            _f("SEED", "Seed", "str", description="Empty for a random world.", group="Game"),
            _f("RCON_PASSWORD", "RCON password", "secret", description="Generated when empty; GameFleet keeps it for console access.", group="Access"),
        ),
        (DeployPort(label="game", container_port=25565, protocol="tcp", default_host_port=25565),
         DeployPort(label="rcon", container_port=25575, protocol="tcp", default_host_port=None)),
        (("data", "/data"),), 120, {"EULA": "TRUE", "ENABLE_RCON": "true"}, "1000:1000", "RCON_PASSWORD",
    ),
    "minecraft_bedrock": Template(
        GameServerType.minecraft_bedrock, "itzg/minecraft-bedrock-server:latest",
        "Bedrock edition for phones, consoles and Windows 10 clients, through itzg/minecraft-bedrock-server.",
        "1 GB RAM",
        (
            _f("SERVER_NAME", "Server name", "str", "Dedicated Server", group="Game"),
            _f("GAMEMODE", "Game mode", "enum", "survival", options=("survival", "creative", "adventure"), group="Game"),
            _f("DIFFICULTY", "Difficulty", "enum", "normal", options=("peaceful", "easy", "normal", "hard"), group="Game"),
            _f("MAX_PLAYERS", "Max players", "int", 10, group="Game"),
            _f("LEVEL_NAME", "World name", "str", "Bedrock level", group="Game"),
            _f("ONLINE_MODE", "Online mode", "bool", True, description="Require Xbox Live accounts.", group="Game"),
            _f("VERSION", "Version", "str", "LATEST", group="Software"),
        ),
        (DeployPort(label="game", container_port=19132, protocol="udp", default_host_port=19132),),
        (("data", "/data"),), 60, {"EULA": "TRUE"}, "1000:1000",
    ),
    "factorio": Template(
        GameServerType.factorio, "factoriotools/factorio:stable",
        "Factorio headless server. A new map is generated on the first start; drop a save into saves/ to use "
        "your own. RCON is enabled with a password the image generates.",
        "1 GB RAM, more for big factories",
        (
            _f("SAVE_NAME", "Save name", "str", description="Empty loads the newest save.", group="Game"),
            _f("GENERATE_NEW_SAVE", "Generate a new map", "bool", True, description="When there is no save yet.", group="Game"),
            _f("LOAD_LATEST_SAVE", "Load the newest save", "bool", True, group="Game"),
            _f("UPDATE_MODS_ON_START", "Update mods on start", "bool", False, description="Needs a Factorio account in the settings file.", group="Software"),
        ),
        (DeployPort(label="game", container_port=34197, protocol="udp", default_host_port=34197),
         DeployPort(label="rcon", container_port=27015, protocol="tcp", default_host_port=27015)),
        (("data", "/factorio"),), 30, {}, "845:845",
    ),
    "valheim": Template(
        GameServerType.valheim, "lloesche/valheim-server:latest",
        "Valheim dedicated server through lloesche/valheim-server, with its own hourly backups and automatic "
        "updates. The server files are downloaded on the first start (about 1 GB).",
        "4 GB RAM",
        (
            _f("SERVER_NAME", "Server name", "str", "My Valheim Server", required=True, group="Game"),
            _f("WORLD_NAME", "World name", "str", "Dedicated", required=True, group="Game"),
            _f("SERVER_PASS", "Password", "secret", required=True, description="At least 5 characters; generated when empty.", group="Access"),
            _f("SERVER_PUBLIC", "Public listing", "bool", False, description="Show in the in-game server browser.", group="Access"),
            _f("BACKUPS", "Hourly backups", "bool", True, group="Game"),
            _f("UPDATE_CRON", "Update check", "str", "*/15 * * * *", description="Cron expression; empty disables.", group="Software"),
        ),
        (DeployPort(label="game", container_port=2456, protocol="udp", default_host_port=2456),
         DeployPort(label="query", container_port=2457, protocol="udp", default_host_port=2457)),
        (("config", "/config"), ("server", "/opt/valheim")), 60, {},
    ),
    "satisfactory": Template(
        GameServerType.satisfactory, "wolveix/satisfactory-server:latest",
        "Satisfactory dedicated server through wolveix/satisfactory-server. The game files are downloaded on "
        "the first start (about 10 GB); claim the server in the in-game Server Manager afterwards.",
        "8 GB RAM and 15 GB disk",
        (
            _f("MAXPLAYERS", "Max players", "int", 4, group="Game"),
            _f("AUTOPAUSE", "Pause when empty", "bool", True, group="Game"),
            _f("AUTOSAVEONDISCONNECT", "Save on disconnect", "bool", True, group="Game"),
            _f("AUTOSAVEINTERVAL", "Autosave interval", "int", 300, description="Seconds.", group="Game"),
            _f("SKIPUPDATE", "Skip updates", "bool", False, description="Do not update the game on start.", group="Software"),
        ),
        (DeployPort(label="game", container_port=7777, protocol="udp", default_host_port=7777),
         DeployPort(label="game-tcp", container_port=7777, protocol="tcp", default_host_port=7777),
         DeployPort(label="api", container_port=8888, protocol="tcp", default_host_port=8888)),
        (("config", "/config"),), 60, {"SERVERGAMEPORT": "7777"},
    ),
}


def templates() -> list[DeployTemplate]:
    return [
        DeployTemplate(id=key, game=t.game, label=GAME_CATALOG[t.game].label, image=t.image, description=t.description,
                       memory_hint=t.memory_hint, fields=list(t.fields), ports=list(t.ports),
                       data_dir=t.volumes[0][1], stop_timeout=t.stop_timeout)
        for key, t in TEMPLATES.items()
    ]


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40].rstrip("-")
    if len(slug) < 2:
        raise DeployError("The name needs at least two letters or digits.")
    return slug


def _env_value(f: DeployField, value: FieldValue) -> Optional[str]:
    """The string for the container environment; None leaves the variable unset."""
    if value is None or value == "":
        if f.type == "secret" and (f.required or f.key.endswith("PASSWORD")):
            return secrets.token_urlsafe(12)
        if f.default is None or f.default == "":
            if f.required:
                raise DeployError(f"{f.label} is required.")
            return None
        value = f.default
    if f.type == "bool":
        if isinstance(value, str):
            value = value.lower() == "true"
        return "true" if value else "false"
    if f.type == "int":
        try:
            return str(int(value))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise DeployError(f"{f.label} must be a whole number.")
    text = str(value)
    if f.type == "enum" and text not in f.options:
        raise DeployError(f"{f.label} must be one of {', '.join(f.options)}.")
    if f.key == "SERVER_PASS" and len(text) < 5:
        raise DeployError("The Valheim password needs at least 5 characters.")
    if "\n" in text:
        raise DeployError(f"{f.label} must be a single line.")
    return text


def _compose_yaml(image: str, container: str, env: dict[str, str], ports: list[tuple[int, int, str, str]],
                  volumes: list[tuple[str, str]], stop_timeout: int) -> str:
    """A compose file equivalent to the created container, for managing it by hand later."""
    def q(value: str) -> str:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    lines = ["# Written by GameFleet. `docker compose up -d` here recreates the same container.",
             "services:", f"  {container}:", f"    image: {image}", f"    container_name: {container}",
             "    restart: unless-stopped", f"    stop_grace_period: {stop_timeout}s", "    environment:"]
    lines += [f"      {key}: {q(value)}" for key, value in env.items()]
    if ports:
        lines.append("    ports:")
        lines += [f'      - "{host}:{cport}/{proto}"' for host, cport, proto, _ in ports]
    lines.append("    volumes:")
    lines += [f"      - ./{sub}:{path}" for sub, path in volumes]
    return "\n".join(lines) + "\n"


class DeployService:
    def __init__(self) -> None:
        self.jobs: dict[str, DeployJob] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def template(self, key: str) -> Template:
        t = TEMPLATES.get(key)
        if t is None:
            raise DeployError("Unknown template.")
        return t

    def _ports(self, t: Template, host_ports: dict[str, int]) -> list[tuple[int, int, str, str]]:
        """(host port, container port, protocol, label) for every port the user publishes."""
        result = []
        seen: set[tuple[int, str]] = set()
        for p in t.ports:
            host = host_ports.get(p.label, p.default_host_port)
            if host is None:
                continue
            if not 1 <= int(host) <= 65535:
                raise DeployError(f"Port {host} for {p.label} is out of range.")
            if (int(host), p.protocol) in seen:
                raise DeployError(f"Host port {host}/{p.protocol} is used twice.")
            seen.add((int(host), p.protocol))
            result.append((int(host), p.container_port, p.protocol, p.label))
        return result

    async def check(self, template: str, name: str, host_ports: dict[str, int]) -> DeployCheckResult:
        if not os.path.isabs(SERVERS_ROOT):
            raise DeployError(f"SERVERS_ROOT must be an absolute path on the host (got {SERVERS_ROOT}).")
        t = self.template(template)
        slug = slugify(name)
        ports = self._ports(t, host_ports)
        name_free = await docker_service.get_raw(slug) is None
        conflicts, warnings = [], []
        wanted = {(host, proto): label for host, _, proto, label in ports}
        seen: set[tuple[int, str, str]] = set()
        for binding in await docker_service.host_bindings():
            label = wanted.get((binding["port"], binding["protocol"]))
            key = (binding["port"], binding["protocol"], binding["container"])
            if label is None or key in seen:  # IPv4 and IPv6 bindings of one port count once
                continue
            seen.add(key)
            issue = PortIssue(label=label, port=binding["port"], protocol=binding["protocol"],
                              container=binding["container"], state=binding["state"] or "unknown")
            (conflicts if binding["state"] == "running" else warnings).append(issue)
        return DeployCheckResult(slug=slug, name_free=name_free, directory=f"{SERVERS_ROOT}/{t.game.value}/{slug}",
                                 conflicts=conflicts, warnings=warnings)

    async def deploy(self, request: DeployRequest) -> DeployJob:
        """Validate everything that can be validated up front, then run the rest in the background."""
        check = await self.check(request.template, request.name, request.host_ports)
        t = self.template(request.template)
        if not check.name_free:
            raise DeployError(f"A container named {check.slug} already exists.")
        if check.conflicts:
            holders = ", ".join(f"{c.port}/{c.protocol} by {c.container}" for c in check.conflicts)
            raise DeployError(f"Port in use: {holders}.")
        known = {f.key for f in t.fields}
        unknown = set(request.values) - known
        if unknown:
            raise DeployError(f"Unknown setting: {', '.join(sorted(unknown))}.")
        env = dict(t.fixed_env)
        for f in t.fields:
            value = _env_value(f, request.values.get(f.key))
            if value is not None:
                env[f.key] = value
        ports = self._ports(t, request.host_ports)
        job = DeployJob(id=uuid.uuid4().hex[:12], template=request.template, name=request.name.strip(),
                        container_name=check.slug, directory=check.directory, started_at=time.time())
        self.jobs[job.id] = job
        for old in [j for j in self.jobs.values() if j.finished_at][:-JOB_KEEP]:
            self.jobs.pop(old.id, None)
        self._tasks[job.id] = asyncio.create_task(self._run(job, t, env, ports, request))
        return job

    async def _run(self, job: DeployJob, t: Template, env: dict[str, str], ports: list[tuple[int, int, str, str]],
                   request: DeployRequest) -> None:
        container_id: Optional[str] = None
        try:
            job.phase = "pulling"
            job.detail = t.image

            def progress(done: int, seen: int) -> None:
                job.progress = done / seen if seen else None
                job.detail = f"{t.image}: {done}/{seen} layers"
            try:
                await docker_service.pull(t.image, progress)
            except docker.errors.APIError as exc:
                raise DeployError(f"Could not pull {t.image}: {exc.explanation or exc}")
            except OSError as exc:
                raise DeployError(f"Could not pull {t.image}: {exc}")

            job.phase, job.progress, job.detail = "creating", None, "writing docker-compose.yml"
            await self._prepare_directory(job, t, env, ports)
            job.detail = "creating the container"
            container_id = await docker_service.create_container(
                image=t.image, name=job.container_name, environment=env,
                ports=[(cport, proto) for _, cport, proto, _ in ports],
                stop_timeout=t.stop_timeout,
                host_config={
                    "binds": [f"{job.directory}/{sub}:{path}" for sub, path in t.volumes],
                    "port_bindings": {f"{cport}/{proto}": host for host, cport, proto, _ in ports},
                    "restart_policy": {"Name": "unless-stopped"},
                },
            )
            if request.start:
                job.phase, job.detail = "starting", None
                await docker_service.start(job.container_name)
            job.phase, job.detail = "importing", None
            async with async_session() as session:
                job.server_id = await self._import(session, job, t, env, request)
            job.phase, job.detail = "done", None
        except DeployError as exc:
            await self._fail(job, container_id, str(exc))
        except docker.errors.APIError as exc:
            await self._fail(job, container_id, f"Docker refused the request: {exc.explanation or exc}")
        except Exception as exc:  # unexpected: keep the message for the UI, the trace for the log
            log.exception("Deploy %s failed", job.container_name)
            await self._fail(job, container_id, f"{type(exc).__name__}: {exc}")
        finally:
            job.finished_at = time.time()
            self._tasks.pop(job.id, None)

    async def _fail(self, job: DeployJob, container_id: Optional[str], error: str) -> None:
        job.phase, job.error = "failed", error
        if container_id:
            # Half-made servers are removed so the name and ports are free for the next try; the data
            # directory stays, so a download that already happened is not lost.
            try:
                await docker_service.remove_container(job.container_name)
            except Exception as exc:
                log.warning("Could not remove %s after a failed deploy: %s", job.container_name, exc)

    async def _prepare_directory(self, job: DeployJob, t: Template, env: dict[str, str],
                                 ports: list[tuple[int, int, str, str]]) -> None:
        """Create `<root>/<game>/<slug>` with the data subdirectories owned by the image's user and a
        compose file; done through a helper container that mounts the directory (Docker creates it)."""
        helper = f"{HELPER_PREFIX}deploy-{job.container_name}"
        compose = _compose_yaml(t.image, job.container_name, env, ports, list(t.volumes), t.stop_timeout)
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            info = tarfile.TarInfo("docker-compose.yml")
            payload = compose.encode()
            info.size, info.mtime, info.mode = len(payload), int(time.time()), 0o644
            tar.addfile(info, io.BytesIO(payload))
        await docker_service.remove_container(helper)
        await docker_service.create_container(
            image=t.image, name=helper, entrypoint=["sleep"], command=["300"], user="root",
            host_config={"binds": [f"{job.directory}:{ROOT_MOUNT}"], "network_mode": "none"},
        )
        try:
            await docker_service.start(helper)
            script = 'for d in $D; do mkdir -p "$d"; [ -n "$O" ] && chown "$O" "$d"; done; exit 0'
            code, output = await docker_service.shell(
                helper, script, {"D": " ".join(f"{ROOT_MOUNT}/{sub}" for sub, _ in t.volumes), "O": t.owner or ""})
            if code != 0:
                raise DeployError(f"Could not prepare {job.directory}: {output.strip()}")
            await docker_service.put_archive(helper, ROOT_MOUNT, buf.getvalue())
        finally:
            await docker_service.remove_container(helper)

    async def _import(self, session: AsyncSession, job: DeployJob, t: Template, env: dict[str, str],
                      request: DeployRequest) -> str:
        from gamefleet_backend.services.docker_discovery_service import DockerDiscoveryService  # circular at module level

        raw = await docker_service.get_raw(job.container_name)
        if raw is None:
            raise DeployError("The container disappeared before it could be imported.")
        server = await DockerDiscoveryService(session).import_container(raw, game=t.game, name=job.name)
        server.is_public = request.is_public
        if t.rcon_env and env.get(t.rcon_env):
            server.rcon_password = env[t.rcon_env]
        session.add(server)
        await session.commit()
        return server.id


def validate_root() -> Optional[str]:
    """Why deploys would fail with the current SERVERS_ROOT, or None."""
    if not os.path.isabs(SERVERS_ROOT) or posixpath.normpath(SERVERS_ROOT) != SERVERS_ROOT:
        return f"SERVERS_ROOT must be a normalised absolute path on the host (got {SERVERS_ROOT!r})."
    return None


deploy_service = DeployService()
