"""Thin async wrapper around the Docker Engine API (docker-py is synchronous, so calls run in a thread).

Everything here works on the *list* representation of containers (one API call, no per-container inspect)
except where the full config is needed (environment variables for RCON passwords).
"""
import asyncio
import io
import logging
import os
import re
import tarfile
import time
from typing import Any, Optional

import docker
import docker.errors

from gamefleet_backend.models.container_info import ContainerInfo, ContainerMount, HostStats, PortBinding

log = logging.getLogger(__name__)

# Imported containers are queried through this address (host.docker.internal from the backend container).
SERVER_ADDRESS = os.getenv("DOCKER_SERVER_ADDRESS", "127.0.0.1")
STATS_MIN_INTERVAL = float(os.getenv("DOCKER_STATS_INTERVAL", "10"))  # seconds between two stats samples
SIZES_MIN_INTERVAL = float(os.getenv("DOCKER_SIZES_INTERVAL", "300"))  # `du` is the expensive part
COMPOSE_PROJECT, COMPOSE_DIR = "com.docker.compose.project", "com.docker.compose.project.working_dir"
# An image whose tag moved to a newer pull is listed by its bare id.
IMAGE_ID = re.compile(r"^(sha256:)?[0-9a-f]{12,64}$")
WILDCARD_IPS = {"", "0.0.0.0", "::"}
STATES_MAX_AGE = 5.0  # seconds the container-state snapshot is shared between live queries
POWER_TIMEOUT = 45  # seconds a container gets to shut down cleanly before it is killed


def map_container(c: dict[str, Any]) -> ContainerInfo:
    seen: set[tuple[int, str]] = set()
    ports: list[PortBinding] = []
    for p in c.get("Ports") or []:
        key = (int(p["PrivatePort"]), p.get("Type", "tcp"))
        if key in seen:
            continue  # IPv4 and IPv6 bindings of the same port
        seen.add(key)
        ports.append(PortBinding(container_port=key[0], host_port=p.get("PublicPort"), protocol=key[1]))
    mounts = [
        ContainerMount(type=m.get("Type", ""), source=m.get("Name") or m.get("Source", ""), destination=m.get("Destination", ""))
        for m in c.get("Mounts") or []
    ]
    return ContainerInfo(
        id=c["Id"],
        name=(c.get("Names") or ["/?"])[0].lstrip("/"),
        image=c.get("Image", ""),
        state=c.get("State", "unknown"),
        status=c.get("Status", ""),
        ports=sorted(ports, key=lambda p: (p.container_port, p.protocol)),
        mounts=mounts,
        labels=c.get("Labels") or {},
        compose_project=(c.get("Labels") or {}).get(COMPOSE_PROJECT),
        compose_dir=(c.get("Labels") or {}).get(COMPOSE_DIR),
    )


def bindings_from_inspect(attrs: dict[str, Any]) -> list[dict[str, Any]]:
    """Configured port bindings in the list API's `Ports` shape (they exist whether the container runs or not)."""
    ports: list[dict[str, Any]] = []
    bound = (attrs.get("HostConfig") or {}).get("PortBindings") or {}
    for spec, targets in bound.items():
        private, _, proto = spec.partition("/")
        for target in targets or []:
            if target.get("HostPort"):
                ports.append({"PrivatePort": int(private), "PublicPort": int(target["HostPort"]),
                              "Type": proto or "tcp", "IP": target.get("HostIp") or "0.0.0.0"})
    for spec in (attrs.get("Config") or {}).get("ExposedPorts") or {}:
        if spec not in bound:
            private, _, proto = spec.partition("/")
            ports.append({"PrivatePort": int(private), "Type": proto or "tcp"})
    return ports


def container_ip(c: dict[str, Any]) -> Optional[str]:
    for network in (c.get("NetworkSettings") or {}).get("Networks", {}).values():
        if ip := network.get("IPAddress"):
            return ip
    return None


def network_mode(c: dict[str, Any]) -> str:
    return (c.get("HostConfig") or {}).get("NetworkMode", "")


class DockerUnavailable(Exception):
    pass


class DockerService:
    """One instance per process; `available` is re-checked lazily so a daemon that comes up later is picked up."""

    def __init__(self):
        self._client: Optional[docker.DockerClient] = None
        self._error: Optional[str] = None
        self._checked_at = 0.0
        # Per container: last raw stats sample (for CPU deltas), last HostStats, last sizes.
        self._samples: dict[str, dict[str, Any]] = {}
        self._stats: dict[str, HostStats] = {}
        self._sizes: dict[str, tuple[float, Optional[int], Optional[int]]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        # name -> state of every container, from one list call (live queries ask per server, in parallel).
        self._states: Optional[tuple[float, dict[str, str]]] = None
        self._states_lock = asyncio.Lock()
        # Container id -> what `complete` learned from inspect. Image and bindings never change for an id.
        self._completed: dict[str, dict[str, Any]] = {}

    # ---- connection -------------------------------------------------------------------------------------

    def _connect(self) -> docker.DockerClient:
        if self._client is None and (self._error is None or time.monotonic() - self._checked_at > 30):
            self._checked_at = time.monotonic()
            try:
                client = docker.from_env(timeout=20)
                client.ping()
                self._client = client
                self._error = None
            except Exception as exc:  # DockerException, requests errors
                self._error = f"{type(exc).__name__}: {exc}"
                log.warning("Docker daemon unavailable: %s", self._error)
        if self._client is None:
            raise DockerUnavailable(self._error or "Docker daemon unavailable")
        return self._client

    async def status(self) -> tuple[bool, Optional[str]]:
        try:
            await asyncio.to_thread(self._connect)
            return True, None
        except DockerUnavailable as exc:
            return False, str(exc)

    async def _call(self, fn, *args, **kwargs):
        client = await asyncio.to_thread(self._connect)
        try:
            return await asyncio.to_thread(fn, client, *args, **kwargs)
        except docker.errors.NotFound:
            raise
        except (docker.errors.APIError, docker.errors.DockerException, OSError) as exc:
            # Connection problems mean the daemon went away; force a reconnect on the next call.
            if not isinstance(exc, docker.errors.APIError):
                self._client = None
            raise

    # ---- listing --------------------------------------------------------------------------------------

    async def list_raw(self) -> list[dict[str, Any]]:
        return await self._call(lambda c: c.api.containers(all=True))

    async def get_raw(self, name: str) -> Optional[dict[str, Any]]:
        containers = await self._call(lambda c: c.api.containers(all=True, filters={"name": f"^/{name}$"}))
        return containers[0] if containers else None

    async def complete(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Fill the gaps of the list representation from inspect: a stopped container lists no published
        ports, and an image whose tag moved on is listed by id. Hosts with many instances of one game,
        most of them stopped, need both to be told apart and mapped to the right port."""
        ports = raw.get("Ports") or []
        needs_ports = raw.get("State") != "running" and not any(p.get("PublicPort") for p in ports)
        needs_image = bool(IMAGE_ID.match(raw.get("Image", "")))
        if not (needs_ports or needs_image):
            return raw
        patch = self._completed.get(raw["Id"])
        if patch is None:
            try:
                attrs = await self.inspect(raw["Id"])
            except (docker.errors.DockerException, OSError):
                return raw
            patch = {"Image": (attrs.get("Config") or {}).get("Image"), "Ports": bindings_from_inspect(attrs)}
            self._completed[raw["Id"]] = patch
        result = dict(raw)
        if needs_image and patch["Image"]:
            result["Image"] = patch["Image"]
        if needs_ports and patch["Ports"]:
            result["Ports"] = patch["Ports"]
        return result

    async def port_conflicts(self, name: str) -> dict[str, list[str]]:
        """Running containers that hold a host port this container wants: {container: ["25565/tcp"]}.
        Only Docker's own bindings are visible from here; a port taken by a host process surfaces when
        Docker refuses the start."""
        attrs = await self.inspect(name)
        wanted = [p for p in bindings_from_inspect(attrs) if p.get("PublicPort")]
        conflicts: dict[str, list[str]] = {}
        for other in await self.list_raw():
            other_name = map_container(other).name
            if other.get("State") != "running" or other["Id"] == attrs.get("Id"):
                continue
            for held in other.get("Ports") or []:
                for want in wanted:
                    if (held.get("PublicPort") == want["PublicPort"] and held.get("Type", "tcp") == want["Type"]
                            and (held.get("IP", "") in WILDCARD_IPS or want["IP"] in WILDCARD_IPS or held.get("IP") == want["IP"])):
                        label = f"{want['PublicPort']}/{want['Type']}"
                        if label not in conflicts.setdefault(other_name, []):
                            conflicts[other_name].append(label)
        return conflicts

    async def states(self) -> Optional[dict[str, str]]:
        """State of every container by name, or None when Docker cannot be asked."""
        async with self._states_lock:
            if self._states is None or time.monotonic() - self._states[0] > STATES_MAX_AGE:
                try:
                    containers = await self.list_raw()
                except (DockerUnavailable, docker.errors.DockerException, OSError):
                    return None
                self._states = (time.monotonic(), {map_container(c).name: c.get("State", "unknown") for c in containers})
            return self._states[1]

    async def inspect(self, name: str) -> dict[str, Any]:
        return await self._call(lambda c: c.api.inspect_container(name))

    async def env(self, name: str) -> dict[str, str]:
        data = await self.inspect(name)
        result = {}
        for entry in (data.get("Config") or {}).get("Env") or []:
            key, _, value = entry.partition("=")
            result[key] = value
        return result

    async def read_file(self, name: str, path: str, limit: int = 4096) -> Optional[str]:
        """Read a small text file from a running container without exec (uses the archive endpoint)."""
        def read(c: docker.DockerClient) -> Optional[str]:
            stream, _ = c.api.get_archive(name, path)
            data = b"".join(stream)
            with tarfile.open(fileobj=io.BytesIO(data)) as tar:
                for member in tar.getmembers():
                    if member.isfile():
                        f = tar.extractfile(member)
                        return f.read(limit).decode("utf-8", errors="replace") if f else None
            return None
        try:
            return await self._call(read)
        except docker.errors.NotFound:
            return None

    # ---- power ----------------------------------------------------------------------------------------

    async def power(self, name: str, action: str) -> dict[str, Any]:
        def run(c: docker.DockerClient):
            container = c.containers.get(name)
            # A longer stop_grace_period from the compose file wins: big worlds need their time to save.
            timeout = max(POWER_TIMEOUT, (container.attrs.get("Config") or {}).get("StopTimeout") or 0)
            match action:
                case "start":
                    container.start()
                case "stop":
                    container.stop(timeout=timeout)
                case "restart":
                    container.restart(timeout=timeout)
                case _:
                    raise ValueError(f"Unknown action {action}")
            container.reload()
            return container.attrs
        return await self._call(run)

    # ---- stats ----------------------------------------------------------------------------------------

    async def host_stats(self, name: str, data_path: Optional[str], world_path: Optional[str]) -> HostStats:
        """CPU/memory from one `stats` sample per call (deltas against the previous call give CPU%),
        directory sizes from an occasional `du` inside the container. Both are cached per container."""
        lock = self._locks.setdefault(name, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            cached = self._stats.get(name)
            if cached and now - cached.sampled_at < STATS_MIN_INTERVAL:
                return cached
            try:
                stats = await self._sample(name, now)
            except docker.errors.NotFound:
                stats = HostStats(container_name=name, state="missing", status="Container not found",
                                  sampled_at=now, error="Container not found")
            except Exception as exc:
                stats = HostStats(container_name=name, state="unknown", status="", sampled_at=now,
                                  error=f"{type(exc).__name__}: {exc}")
            if stats.state == "running" and (data_path or world_path):
                sizes = self._sizes.get(name)
                if sizes is None or now - sizes[0] > SIZES_MIN_INTERVAL:
                    sizes = (now, *await self._du(name, data_path, world_path))
                    self._sizes[name] = sizes
                stats.sizes_sampled_at, stats.data_size, stats.world_size = sizes
            self._stats[name] = stats
            return stats

    async def _sample(self, name: str, now: float) -> HostStats:
        def fetch(c: docker.DockerClient):
            attrs = c.api.inspect_container(name)
            state = attrs["State"]
            raw = c.api.stats(name, stream=False, one_shot=True) if state.get("Running") else None
            return attrs, raw
        attrs, raw = await self._call(fetch)
        state = attrs["State"]
        result = HostStats(
            container_name=name,
            state=state.get("Status", "unknown"),
            status="running" if state.get("Running") else state.get("Status", ""),
            started_at=state.get("StartedAt") if state.get("Running") else None,
            sampled_at=now,
            compose_project=((attrs.get("Config") or {}).get("Labels") or {}).get(COMPOSE_PROJECT),
            compose_dir=((attrs.get("Config") or {}).get("Labels") or {}).get(COMPOSE_DIR),
        )
        if raw is None:
            self._samples.pop(name, None)
            return result

        cpu = raw.get("cpu_stats") or {}
        usage = (cpu.get("cpu_usage") or {}).get("total_usage")
        system = cpu.get("system_cpu_usage")
        online = cpu.get("online_cpus") or len((cpu.get("cpu_usage") or {}).get("percpu_usage") or []) or os.cpu_count() or 1
        previous = self._samples.get(name)
        if previous and usage is not None and system is not None and previous.get("started") == state.get("StartedAt"):
            cpu_delta = usage - previous["usage"]
            system_delta = system - previous["system"]
            if cpu_delta >= 0 and system_delta > 0:
                result.cpu_percent = round(cpu_delta / system_delta * online * 100, 1)
        self._samples[name] = {"usage": usage, "system": system, "started": state.get("StartedAt")}

        host_config = attrs.get("HostConfig") or {}
        nano = host_config.get("NanoCpus") or 0
        quota, period = host_config.get("CpuQuota") or 0, host_config.get("CpuPeriod") or 100000
        result.cpu_limit = nano / 1e9 if nano else (quota / period if quota > 0 else float(online))

        mem = raw.get("memory_stats") or {}
        if (used := mem.get("usage")) is not None:
            inner = mem.get("stats") or {}
            # Like `docker stats`: leave out the page cache (cgroup v2 "inactive_file", v1 "total_inactive_file").
            cache = inner.get("inactive_file", inner.get("total_inactive_file", 0)) or 0
            result.memory_used = max(0, used - cache)
            result.memory_limit = mem.get("limit")
        return result

    async def _du(self, name: str, data_path: Optional[str], world_path: Optional[str]) -> tuple[Optional[int], Optional[int]]:
        def run(c: docker.DockerClient) -> list[Optional[int]]:
            container = c.containers.get(name)
            sizes: list[Optional[int]] = []
            # One `du` per path: given nested paths in one call, du counts the inner one only once.
            # -k is understood by both GNU and busybox du.
            for path in (data_path, world_path):
                if not path:
                    sizes.append(None)
                    continue
                code, output = container.exec_run(["du", "-sk", path], user="root")
                first = output.decode("utf-8", errors="replace").split(None, 1)[0] if output.strip() else ""
                if code == 0 and first.isdigit():
                    sizes.append(int(first) * 1024)
                else:
                    log.info("du %s in %s failed (%s): %s", path, name, code, output[:200])
                    sizes.append(None)
            return sizes

        try:
            data_size, world_size = await self._call(run)
        except Exception as exc:
            log.info("Could not measure sizes in %s: %s", name, exc)
            return None, None
        return data_size, world_size

    def forget(self, name: str) -> None:
        for store in (self._samples, self._stats, self._sizes, self._locks):
            store.pop(name, None)
        self._states = None


docker_service = DockerService()
