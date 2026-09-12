"""Finds game servers among the Docker containers on this host and links them to GameFleet servers.

A container becomes a GameFleet server with ``source = "docker"`` and ``container_name`` set. The name
is the link (compose keeps it across recreations, the id does not). Containers with ``gamefleet.*``
labels are always imported; containers whose image is in IMAGE_CATALOG are imported when
DOCKER_AUTO_IMPORT is on; keyword and port guesses are only offered in the UI.
"""
import asyncio
import logging
import os
from typing import Any, Optional

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

load_dotenv()

from gamefleet_backend.db.models.game_server import GameServer, IgnoredContainer
from gamefleet_backend.db.session import async_session
from gamefleet_backend.models.container_catalog import LABELS, lookup_image, lookup_keyword, NEVER
from gamefleet_backend.models.container_info import ContainerInfo, DetectedGame, DiscoveredContainer
from gamefleet_backend.models.game_server_type import GAME_CATALOG, GameServerType, QueryProtocol
from gamefleet_backend.services.docker_service import (
    DockerUnavailable, SERVER_ADDRESS, container_ip, docker_service, map_container, network_mode,
)

log = logging.getLogger(__name__)

AUTO_IMPORT = os.getenv("DOCKER_AUTO_IMPORT", "true").lower() in ("1", "true", "yes", "on")
DISCOVERY_INTERVAL = float(os.getenv("DOCKER_DISCOVERY_INTERVAL", "60"))  # seconds; 0 disables the loop
AUTO_IMPORT_CONFIDENCE = {"label", "image"}


def _label_int(labels: dict[str, str], key: str) -> Optional[int]:
    value = labels.get(LABELS[key])
    return int(value) if value and value.isdigit() else None


def _game_from_labels(labels: dict[str, str]) -> Optional[GameServerType]:
    value = labels.get(LABELS["game"])
    if not value:
        return None
    try:
        return GameServerType(value.strip().lower())
    except ValueError:
        log.warning("Container label %s=%r is not a known game", LABELS["game"], value)
        return None


def _game_from_ports(info: ContainerInfo) -> Optional[GameServerType]:
    exposed = {p.container_port for p in info.ports}
    matches = [game for game, spec in GAME_CATALOG.items() if spec.default_port in exposed]
    return matches[0] if len(matches) == 1 else None


def detect(raw: dict[str, Any]) -> Optional[DetectedGame]:
    """Fingerprint one container (list representation). None when it does not look like a game server."""
    info = map_container(raw)
    labels = info.labels
    if labels.get(LABELS["ignore"], "").lower() == "true":
        return None
    if NEVER.search(info.image) or NEVER.search(info.name):
        return None

    reasons: list[str] = []
    fingerprint = lookup_image(info.image)
    game = _game_from_labels(labels)
    if game:
        confidence = "label"
        reasons.append(f"label {LABELS['game']}={game.value}")
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
        fingerprint = None  # the label overrides the image; do not mix in the image's paths

    # Ports inside the container: label > image knowledge > game defaults.
    port = _label_int(labels, "port") or (fingerprint.port if fingerprint else None) or spec.default_port
    query_port = _label_int(labels, "query_port") or (fingerprint.query_port if fingerprint else None)
    if query_port is None and spec.protocol == QueryProtocol.a2s:
        query_port = spec.resolve_query_port(port, None)
    rcon_port = _label_int(labels, "rcon_port") or (fingerprint.rcon_port if fingerprint else None) or spec.default_rcon_port

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

    has_password = any(labels.get(LABELS[k]) for k in ("rcon_password", "rcon_password_env", "rcon_password_file")) or bool(
        fingerprint and (fingerprint.rcon_password_env or fingerprint.rcon_password_file)
    )
    data_path = labels.get(LABELS["data_path"]) or (fingerprint.data_path if fingerprint else None)
    if not data_path and info.mounts:
        data_path = info.mounts[0].destination
    world_path = labels.get(LABELS["world_path"]) or (fingerprint.world_path if fingerprint else None)

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
        name=labels.get(LABELS["name"]) or info.name,
    )


async def resolve_rcon_password(name: str, labels: dict[str, str], image: str) -> Optional[str]:
    """Label value, else the container's environment variable, else a file inside the container."""
    if direct := labels.get(LABELS["rcon_password"]):
        return direct
    fingerprint = lookup_image(image)
    env_name = labels.get(LABELS["rcon_password_env"]) or (fingerprint.rcon_password_env if fingerprint else None)
    if env_name:
        env = await docker_service.env(name)
        if value := env.get(env_name):
            return value
    file_path = labels.get(LABELS["rcon_password_file"]) or (fingerprint.rcon_password_file if fingerprint else None)
    if file_path:
        content = await docker_service.read_file(name, file_path)
        if content and content.strip():
            return content.strip().splitlines()[0]
    return None


class DockerDiscoveryService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _linked(self) -> dict[str, GameServer]:
        rows = (await self.session.execute(select(GameServer).where(GameServer.source == "docker"))).scalars().all()
        return {row.container_name: row for row in rows if row.container_name}

    async def _ignored(self) -> set[str]:
        return {row.container_name for row in (await self.session.execute(select(IgnoredContainer))).scalars().all()}

    async def discover(self, auto_import: bool = AUTO_IMPORT) -> list[DiscoveredContainer]:
        """List candidate containers, importing the certain ones. Raises DockerUnavailable."""
        raw_containers = await docker_service.list_raw()
        linked, ignored = await self._linked(), await self._ignored()
        results: list[DiscoveredContainer] = []
        for raw in raw_containers:
            info = map_container(raw)
            detected = detect(raw)
            server = linked.get(info.name)
            if detected is None and server is None:
                continue
            if server is None and detected and info.name not in ignored and (
                detected.confidence == "label" or (auto_import and detected.confidence in AUTO_IMPORT_CONFIDENCE)
            ):
                server = await self.import_container(raw, detected)
                log.info("Imported container %s as %s (%s)", info.name, detected.game.value, detected.confidence)
            results.append(DiscoveredContainer(
                container=info, detected=detected, server_id=server.id if server else None, ignored=info.name in ignored
            ))
        return results

    async def import_container(self, raw: dict[str, Any], detected: Optional[DetectedGame] = None,
                               game: Optional[GameServerType] = None, name: Optional[str] = None) -> GameServer:
        """Create (or re-sync) the GameFleet server for a container."""
        info = map_container(raw)
        if game and (detected is None or detected.game != game):
            # The user picked a different game than detected: re-run detection as if it were labelled.
            raw = {**raw, "Labels": {**(raw.get("Labels") or {}), LABELS["game"]: game.value}}
            detected = detect(raw)
        if detected is None:
            raise ValueError("Container does not look like a supported game server")

        password = None
        if detected.has_rcon_password:
            try:
                password = await resolve_rcon_password(info.name, info.labels, info.image)
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
        return server

    async def set_ignored(self, container_name: str, ignored: bool) -> None:
        if ignored:
            await self.session.merge(IgnoredContainer(container_name=container_name))
        else:
            await self.session.execute(IgnoredContainer.__table__.delete().where(IgnoredContainer.container_name == container_name))
        await self.session.commit()


async def discovery_loop() -> None:
    """Background task: keeps labelled/known containers imported even when nobody has the dashboard open."""
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
