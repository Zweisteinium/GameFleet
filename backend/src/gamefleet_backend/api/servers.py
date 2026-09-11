from fastapi import APIRouter, Depends, HTTPException
from typing import Sequence
from pydantic import BaseModel, Field

from gamefleet_backend.models.game_server_type import GameServerType, GAME_CATALOG, QueryProtocol
from gamefleet_backend.db.models.game_server import GameServer, GameServerPublic
from gamefleet_backend.services.game_server_service import GameServerService
from gamefleet_backend.services.live_server_info_service import LiveServerInfoService
from gamefleet_backend.dependencies import get_game_server_service
from gamefleet_backend.models.server_info import LiveServerInfo


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
    service: GameServerService = Depends(get_game_server_service)
):
    """Delete a game server."""
    success = await service.delete_server(server_id)
    if not success:
        raise HTTPException(status_code=404, detail="Server not found")
    return {"message": "Server deleted successfully"}


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
