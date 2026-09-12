import asyncio
from typing import Literal, Sequence

import docker.errors
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from gamefleet_backend.db.models.game_server import GameServer, GameServerPublic
from gamefleet_backend.dependencies import get_docker_discovery_service, get_game_server_service
from gamefleet_backend.models.container_info import HostStats
from gamefleet_backend.models.game_server_type import GAME_CATALOG, GameServerType, QueryProtocol
from gamefleet_backend.models.server_info import LiveServerInfo
from gamefleet_backend.services.docker_discovery_service import DockerDiscoveryService
from gamefleet_backend.services.docker_service import DockerUnavailable, docker_service
from gamefleet_backend.services.game_server_service import GameServerService
from gamefleet_backend.services.live_server_info_service import LiveServerInfoService


router = APIRouter()


class GameServerCreate(BaseModel):
    name: str
    game: GameServerType
    address: str
    port: int = Field(ge=1, le=65535)
    query_port: int | None = Field(default=None, ge=1, le=65535)
    rcon_port: int | None = Field(default=None, ge=1, le=65535)
    rcon_password: str | None = None


class GameServerUpdate(BaseModel):
    name: str | None = None
    game: GameServerType | None = None
    address: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    query_port: int | None = Field(default=None, ge=1, le=65535)
    rcon_port: int | None = Field(default=None, ge=1, le=65535)
    rcon_password: str | None = None


class PowerRequest(BaseModel):
    action: Literal["start", "stop", "restart"]


class GameTypeInfo(BaseModel):
    type: GameServerType
    label: str
    protocol: QueryProtocol
    default_port: int
    default_query_port: int | None
    default_rcon_port: int | None
    needs_rcon: bool


@router.get('', response_model=Sequence[GameServerPublic], operation_id="getServers")
async def get_servers(
    service: GameServerService = Depends(get_game_server_service)
):
    """Get all game servers from the database."""
    return [GameServerPublic.from_server(s) for s in await service.get_all_servers()]


@router.post('', response_model=GameServerPublic, operation_id="postServer")
async def post_server(
    server_data: GameServerCreate,
    service: GameServerService = Depends(get_game_server_service)
):
    """Create a new game server."""
    return GameServerPublic.from_server(await service.create_server(server_data.model_dump()))


@router.get("/supported_types", response_model=Sequence[GameServerType], operation_id="getSupportedServerTypes")
def supported_types() -> list[GameServerType]:
    """Get list of supported game server types."""
    return list(GameServerType)


@router.get("/game-types", response_model=Sequence[GameTypeInfo], operation_id="getGameTypes")
def game_types() -> list[GameTypeInfo]:
    """Get supported game types with display labels and default ports (for forms)."""
    return [
        GameTypeInfo(
            type=game,
            label=spec.label,
            protocol=spec.protocol,
            default_port=spec.default_port,
            default_query_port=spec.resolve_query_port(spec.default_port, None) if spec.protocol == QueryProtocol.a2s else None,
            default_rcon_port=spec.default_rcon_port,
            needs_rcon=spec.protocol == QueryProtocol.factorio_rcon,
        )
        for game, spec in GAME_CATALOG.items()
    ]


@router.get('/live-info', response_model=dict[str, LiveServerInfo], operation_id="getAllServersLiveInfo")
async def get_all_servers_live_info(
    service: GameServerService = Depends(get_game_server_service)
):
    """Get live information for every server at once (queried concurrently)."""
    servers = await service.get_all_servers()
    return await LiveServerInfoService.get_all_server_info(list(servers))


@router.get('/host-stats', response_model=dict[str, HostStats], operation_id="getAllHostStats")
async def get_all_host_stats(
    service: GameServerService = Depends(get_game_server_service)
):
    """Container state and resource usage for every Docker-linked server (cached per container)."""
    servers = [s for s in await service.get_all_servers() if s.source == "docker" and s.container_name]
    if not servers:
        return {}
    try:
        await docker_service.status()
        results = await asyncio.gather(*(docker_service.host_stats(s.container_name, s.data_path, s.world_path) for s in servers))
    except DockerUnavailable:
        return {}
    return {server.id: stats for server, stats in zip(servers, results)}


@router.get('/by-type/{server_type}', response_model=Sequence[GameServerPublic], operation_id="getServersByType")
async def get_servers_by_type(
    server_type: GameServerType,
    service: GameServerService = Depends(get_game_server_service)
):
    """Get all servers of a specific game type."""
    return [GameServerPublic.from_server(s) for s in await service.get_servers_by_type(server_type)]


@router.get('/{server_id}', response_model=GameServerPublic, operation_id="getServerById")
async def get_server(
    server_id: str,
    service: GameServerService = Depends(get_game_server_service)
):
    """Get a specific game server by ID."""
    server = await service.get_server_by_id(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    return GameServerPublic.from_server(server)


@router.put('/{server_id}', response_model=GameServerPublic, operation_id="updateServer")
async def update_server(
    server_id: str,
    server_data: GameServerUpdate,
    service: GameServerService = Depends(get_game_server_service)
):
    """Update an existing game server (only fields that are sent are changed)."""
    update_data = server_data.model_dump(exclude_unset=True)
    server = await service.update_server(server_id, update_data)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    return GameServerPublic.from_server(server)


@router.delete('/{server_id}', operation_id="deleteServer")
async def delete_server(
    server_id: str,
    service: GameServerService = Depends(get_game_server_service),
    discovery: DockerDiscoveryService = Depends(get_docker_discovery_service),
):
    """Delete a game server. A Docker-linked server's container is hidden from discovery afterwards."""
    server = await service.get_server_by_id(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    if server.source == "docker" and server.container_name:
        # Otherwise discovery would offer (or re-import) the container right away.
        await discovery.set_ignored(server.container_name, True)
        docker_service.forget(server.container_name)
    await service.delete_server(server_id)
    return {"message": "Server deleted successfully"}


async def _docker_server(server_id: str, service: GameServerService) -> GameServer:
    server = await service.get_server_by_id(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    if server.source != "docker" or not server.container_name:
        raise HTTPException(status_code=409, detail="This server is not linked to a Docker container")
    return server


@router.get('/{server_id}/host', response_model=HostStats, operation_id="getServerHostStats")
async def get_server_host_stats(
    server_id: str,
    service: GameServerService = Depends(get_game_server_service)
):
    """Container state, CPU, memory and data sizes of a Docker-linked server."""
    server = await _docker_server(server_id, service)
    try:
        return await docker_service.host_stats(server.container_name, server.data_path, server.world_path)
    except DockerUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Docker daemon unavailable: {exc}")


@router.post('/{server_id}/power', response_model=HostStats, operation_id="powerServer")
async def power_server(
    server_id: str,
    body: PowerRequest,
    service: GameServerService = Depends(get_game_server_service)
):
    """Start, stop or restart the container behind a Docker-linked server."""
    server = await _docker_server(server_id, service)
    try:
        await docker_service.power(server.container_name, body.action)
    except DockerUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Docker daemon unavailable: {exc}")
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found")
    except docker.errors.APIError as exc:
        raise HTTPException(status_code=502, detail=f"Docker refused the request: {exc.explanation or exc}")
    docker_service.forget(server.container_name)
    return await docker_service.host_stats(server.container_name, server.data_path, server.world_path)


@router.get('/{server_id}/live-info', response_model=LiveServerInfo, operation_id="getServerLiveInfoById")
async def get_server_live_info_by_id(
    server_id: str,
    service: GameServerService = Depends(get_game_server_service)
):
    """Get live information for a server by its database ID."""
    server = await service.get_server_by_id(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    return await LiveServerInfoService.get_server_info(server)
