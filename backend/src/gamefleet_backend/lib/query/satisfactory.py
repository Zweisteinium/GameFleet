import asyncio
from typing import cast, TypedDict

from satisfactory_api_client import SatisfactoryAPI
from satisfactory_api_client.exceptions import APIError
from satisfactory_api_client.data.minimum_privilege_level import MinimumPrivilegeLevel

from gamefleet_backend.models.server_info import SatisfactoryServerInfo, ServerStatus
from .common import info_from_exception


class ServerGameState(TypedDict):
    activeSessionName: str
    numConnectedPlayers: int
    playerLimit: int
    techTier: int
    activeSchematic: str
    gamePhase: str
    isGameRunning: bool
    totalGameDuration: int
    isGamePaused: bool
    averageTickRate: float
    autoLoadSessionName: str


def _query_sync(address: str, port: int) -> ServerGameState:
    api = SatisfactoryAPI(host=address, port=port, skip_ssl_verification=True)  # dedicated servers use self-signed certs
    api.passwordless_login(MinimumPrivilegeLevel.CLIENT)
    return cast(ServerGameState, api.query_server_state().data["serverGameState"])


async def get_satisfactory_server_info(address: str, port: int = 7777) -> SatisfactoryServerInfo:
    try:
        # The client library is synchronous (requests), so keep it off the event loop.
        state = await asyncio.wait_for(asyncio.to_thread(_query_sync, address, port), 15)
    except APIError as exc:
        return SatisfactoryServerInfo(status=ServerStatus.UNKNOWN, error_message=f"Server API error: {exc}")
    except Exception as exc:
        return info_from_exception(SatisfactoryServerInfo, exc)

    return SatisfactoryServerInfo(
        status=ServerStatus.ONLINE,
        players_online=state["numConnectedPlayers"],
        players_max=state["playerLimit"],
        game_mode=state.get("gamePhase"),
        session_name=state["activeSessionName"],
        tech_tier=state["techTier"],
        game_phase=state["gamePhase"],
        total_game_duration=state["totalGameDuration"],
        avg_tick_rate=state["averageTickRate"],
        is_paused=state.get("isGamePaused"),
    )
