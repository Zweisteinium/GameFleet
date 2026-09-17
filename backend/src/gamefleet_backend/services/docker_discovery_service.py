"""Finds game servers among the Docker containers on this host and links them to GameFleet servers.

A container becomes a GameFleet server with ``source = "docker"`` and ``container_name`` set. The name
is the link (compose keeps it across recreations, the id does not). Nothing is imported on its own:
the user imports single containers, or all running ones with a known image. Everything is read from the
container itself (image, ports, environment, mounts); GameFleet defines no container labels.
"""
import asyncio
import logging
import os
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from gamefleet_backend.db.models.game_server import GameServer, IgnoredContainer
from gamefleet_backend.db.session import async_session
from gamefleet_backend.models.container_catalog import lookup_image, lookup_keyword, NEVER
from gamefleet_backend.models.container_info import ContainerInfo, DetectedGame, DiscoveredContainer
from gamefleet_backend.models.game_server_type import GAME_CATALOG, GameServerType, QueryProtocol
from gamefleet_backend.services import modpack_service
from gamefleet_backend.services.docker_service import (
    DockerUnavailable, SERVER_ADDRESS, container_ip, docker_service, map_container, network_mode,
)

log = logging.getLogger(__name__)

DISCOVERY_INTERVAL = float(os.getenv("DOCKER_DISCOVERY_INTERVAL", "60"))  # seconds; 0 disables the loop
# Detections that "import all" trusts; name and port guesses are imported one by one after a look.
CERTAIN_CONFIDENCE = {"image"}


def _game_from_ports(info: ContainerInfo) -> Optional[GameServerType]:
    exposed = {p.container_port for p in info.ports}
    matches = [game for game, spec in GAME_CATALOG.items() if spec.default_port in exposed]
    return matches[0] if len(matches) == 1 else None


def detect(raw: dict[str, Any], game: Optional[GameServerType] = None) -> Optional[DetectedGame]:
    """Fingerprint one container (list representation). None when it does not look like a game server.
    `game` is the user's choice (at import, or the game of the linked server) and overrides the guess."""
    info = map_container(raw)
    if NEVER.search(info.image) or NEVER.search(info.name):
        return None

    reasons: list[str] = []
    fingerprint = lookup_image(info.image)
    if game and not (fingerprint and fingerprint.game == game):
        confidence = "manual"
        reasons.append("game chosen by the user")
    elif fingerprint:
        game, confidence = fingerprint.game, "image"
        reasons.append(f"known image {info.image}")
    elif keyword := lookup_keyword(info.image, info.name):
        game, confidence = keyword, "keyword"
        reasons.append("name suggests " + GAME_CATALOG[keyword].label)
    elif port_game := _game_from_ports(info):
        game, confidence = port_game, "port"
        reasons.append(f"exposes port {GAME_CATALOG[port_game].default_port}")
    else:
        return None

    spec = GAME_CATALOG[game]
    if fingerprint and fingerprint.game != game:
        fingerprint = None  # the user's choice overrides the image; do not mix in the image's paths

    # Ports inside the container: image knowledge, else the game's defaults.
    port = (fingerprint.port if fingerprint else None) or spec.default_port
    query_port = fingerprint.query_port if fingerprint else None
    if query_port is None and spec.protocol == QueryProtocol.a2s:
        query_port = spec.resolve_query_port(port, None)
    rcon_port = (fingerprint.rcon_port if fingerprint else None) or spec.default_rcon_port

    # Translate to what is reachable from the host. The game port (and the query/RCON port when the
    # protocol depends on it) must be reachable; an unpublished optional RCON port is simply dropped.
    published = {p.container_port: p.host_port for p in info.ports if p.host_port}
    host_net = network_mode(raw) == "host"
    ip = container_ip(raw)
    required = [port] + ([query_port] if query_port and spec.protocol == QueryProtocol.a2s else [])
    if rcon_port and spec.protocol == QueryProtocol.factorio_rcon:
        required.append(rcon_port)
    wanted = [p for p in (port, query_port, rcon_port) if p]
    if host_net:
        address, mapped = SERVER_ADDRESS, {p: p for p in wanted}
        reasons.append("host network")
    elif all(p in published for p in required):
        address, mapped = SERVER_ADDRESS, {p: published[p] for p in wanted if p in published}
        if published[port] != port:
            reasons.append(f"port {port} published as {published[port]}")
    elif ip:
        address, mapped = ip, {p: p for p in wanted}
        reasons.append(f"unpublished ports, reached via container address {ip}")
    else:
        address, mapped = SERVER_ADDRESS, {p: published.get(p, p) for p in wanted}

    has_password = bool(fingerprint and (fingerprint.rcon_password_env or fingerprint.rcon_password_file))
    data_path = fingerprint.data_path if fingerprint else None
    if not data_path and info.mounts:
        data_path = info.mounts[0].destination
    world_path = fingerprint.world_path if fingerprint else None

    return DetectedGame(
        game=game,
        confidence=confidence,
        reasons=reasons,
        address=address,
        port=mapped[port],
        query_port=mapped.get(query_port) if query_port and query_port != port else None,
        rcon_port=mapped.get(rcon_port) if rcon_port else None,
        has_rcon_password=has_password,
        data_path=data_path,
        world_path=world_path,
        name=info.name,
    )


async def resolve_rcon_password(name: str, image: str) -> Optional[str]:
    """The container's environment variable, else a file inside the container, as the image is known to use."""
    fingerprint = lookup_image(image)
    env_name = fingerprint.rcon_password_env if fingerprint else None
    if env_name:
        env = await docker_service.env(name)
        if value := env.get(env_name):
            return value
    file_path = fingerprint.rcon_password_file if fingerprint else None
    if file_path:
        content = await docker_service.read_file(name, file_path)
        if content and content.strip():
            return content.strip().splitlines()[0]
    return None


class DockerDiscoveryService:
    # container id -> pack named by its environment (None for no pack); shared by all instances.
    _modpacks: dict[str, Optional[modpack_service.Modpack]] = {}

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _linked(self) -> dict[str, GameServer]:
        rows = (await self.session.execute(select(GameServer).where(GameServer.source == "docker"))).scalars().all()
        return {row.container_name: row for row in rows if row.container_name}

    async def _ignored(self) -> set[str]:
        return {row.container_name for row in (await self.session.execute(select(IgnoredContainer))).scalars().all()}

    async def discover(self) -> list[DiscoveredContainer]:
        """List containers that look like game servers; nothing is imported. Raises DockerUnavailable."""
        raw_containers = await docker_service.list_raw()
        linked, ignored = await self._linked(), await self._ignored()
        results: list[DiscoveredContainer] = []
        for raw in raw_containers:
            raw = await docker_service.complete(raw)
            info = map_container(raw)
            server = linked.get(info.name)
            detected = detect(raw, GameServerType(server.game) if server else None)
            if detected is None and server is None:
                continue
            # A container without published ports is reached at its own address, which only exists while it runs.
            if server and detected and detected.game == server.game and info.state == "running":
                await self._sync_endpoint(server, detected)
            if server:
                await self._sync_modpack(server, info.id)
            results.append(DiscoveredContainer(
                container=info, detected=detected, server_id=server.id if server else None, ignored=info.name in ignored
            ))
        return results

    async def import_all(self) -> list[GameServer]:
        """Import every running container that is certainly a game server and neither imported nor hidden.
        Stopped containers are left out: several of them may claim the same host port."""
        raw_by_name = {map_container(raw).name: raw for raw in await docker_service.list_raw()}
        imported: list[GameServer] = []
        for item in await self.discover():
            detected = item.detected
            if (item.server_id or item.ignored or detected is None or item.container.state != "running"
                    or detected.confidence not in CERTAIN_CONFIDENCE):
                continue
            imported.append(await self.import_container(raw_by_name[item.container.name], detected))
            log.info("Imported container %s as %s (%s)", item.container.name, detected.game.value, detected.confidence)
        return imported

    async def _sync_endpoint(self, server: GameServer, detected: DetectedGame) -> None:
        """Follow the container when its reachable address or port mapping changed (compose edits, the backend
        moving between host and bridge networking)."""
        fields = {"address": detected.address, "port": detected.port, "query_port": detected.query_port,
                  "rcon_port": detected.rcon_port}
        changed = {k: v for k, v in fields.items() if getattr(server, k) != v}
        if not changed:
            return
        for key, value in changed.items():
            setattr(server, key, value)
        self.session.add(server)
        await self.session.commit()
        log.info("Updated container %s: %s", server.container_name, ", ".join(f"{k}={v}" for k, v in changed.items()))

    async def _sync_modpack(self, server: GameServer, container_id: str) -> None:
        """Keep the detected modpack of a Minecraft server current. The environment is fixed for the life of a
        container, so each container id is looked at once; a pack typed into the form is left alone."""
        if server.game != GameServerType.minecraft or server.modpack_source == "manual":
            return
        if container_id not in self._modpacks:
            try:
                self._modpacks[container_id] = modpack_service.from_env(await docker_service.env(server.container_name))
            except Exception as exc:  # Docker hiccup: try again on the next run
                log.warning("Could not read the modpack of %s: %s", server.container_name, exc)
                return
        pack = self._modpacks[container_id]
        # The Modrinth side keeps its own cache and retries failures, so a lookup that was down heals itself.
        fields = modpack_service.as_fields(await modpack_service.resolve(pack) if pack else None)
        if server.modpack_icon and not fields["modpack_icon"] and fields["modpack_version"] == server.modpack_version \
                and pack and (pack.modrinth_id or pack.source == "file"):
            return  # Modrinth is unreachable right now: keep the title, link and icon it gave us earlier
        changed = {k: v for k, v in fields.items() if getattr(server, k) != v}
        if changed:
            for key, value in changed.items():
                setattr(server, key, value)
            self.session.add(server)
            await self.session.commit()
            log.info("Modpack of %s: %s", server.container_name, fields["modpack_name"] or "none")

    async def import_container(self, raw: dict[str, Any], detected: Optional[DetectedGame] = None,
                               game: Optional[GameServerType] = None, name: Optional[str] = None) -> GameServer:
        """Create (or re-sync) the GameFleet server for a container."""
        raw = await docker_service.complete(raw)
        info = map_container(raw)
        if detected is None or (game and detected.game != game):
            detected = detect(raw, game)
        if detected is None:
            raise ValueError("Container does not look like a supported game server")

        password = None
        if detected.has_rcon_password:
            try:
                password = await resolve_rcon_password(info.name, info.image)
            except Exception as exc:
                log.warning("Could not read the RCON password of %s: %s", info.name, exc)

        values = dict(
            game=detected.game, address=detected.address, port=detected.port, query_port=detected.query_port,
            rcon_port=detected.rcon_port, data_path=detected.data_path, world_path=detected.world_path,
            source="docker", container_name=info.name,
        )
        server = (await self._linked()).get(info.name)
        if server is None:
            server = GameServer(name=name or detected.name, rcon_password=password, **values)
        else:
            for key, value in values.items():
                setattr(server, key, value)
            if name:
                server.name = name
            if password:
                server.rcon_password = password
        self.session.add(server)
        await self.session.execute(IgnoredContainer.__table__.delete().where(IgnoredContainer.container_name == info.name))
        await self.session.commit()
        await self.session.refresh(server)
        await self._sync_modpack(server, info.id)
        return server

    async def set_ignored(self, container_name: str, ignored: bool) -> None:
        if ignored:
            await self.session.merge(IgnoredContainer(container_name=container_name))
        else:
            await self.session.execute(IgnoredContainer.__table__.delete().where(IgnoredContainer.container_name == container_name))
        await self.session.commit()


async def discovery_loop() -> None:
    """Background task: keeps address and ports of imported containers current when nobody has the dashboard open."""
    while True:
        try:
            async with async_session() as session:
                await DockerDiscoveryService(session).discover()
        except DockerUnavailable:
            pass
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Docker discovery failed")
        await asyncio.sleep(DISCOVERY_INTERVAL)
