"""Generic Steam / Source query (A2S) used by most Steam dedicated servers."""
import asyncio
from typing import Optional

import a2s

from gamefleet_backend.models.server_info import SteamServerInfo, ServerStatus
from .common import QUERY_TIMEOUT, info_from_exception


async def query_a2s(address: str, query_port: int, *, rules: bool = True, players: bool = True) -> tuple:
    """Run A2S_INFO plus (optionally) A2S_RULES and A2S_PLAYER. Rules/players failures are tolerated."""
    target = (address, query_port)
    info = await a2s.ainfo(target, timeout=QUERY_TIMEOUT)
    rules_data, players_data = await asyncio.gather(
        a2s.arules(target, timeout=QUERY_TIMEOUT) if rules else asyncio.sleep(0, result=None),
        a2s.aplayers(target, timeout=QUERY_TIMEOUT) if players else asyncio.sleep(0, result=None),
        return_exceptions=True,
    )
    if isinstance(rules_data, BaseException):
        rules_data = None
    if isinstance(players_data, BaseException):
        players_data = None
    return info, rules_data, players_data


def clean_text(text: Optional[str]) -> Optional[str]:
    """Strip control characters some servers prepend to their names for sorting tricks."""
    if text is None:
        return None
    return "".join(ch for ch in text if ch >= " ").strip() or None


def player_names(players_data) -> Optional[list[str]]:
    if players_data is None:
        return None
    return [name for p in players_data if (name := clean_text(p.name))]


async def get_steam_server_info(address: str, query_port: int) -> SteamServerInfo:
    try:
        info, rules, players = await query_a2s(address, query_port)
    except Exception as exc:
        return info_from_exception(SteamServerInfo, exc)

    return SteamServerInfo(
        status=ServerStatus.ONLINE,
        latency=info.ping * 1000,
        version=info.version or None,
        server_name=clean_text(info.server_name),
        map_name=info.map_name or None,
        password_protected=info.password_protected,
        anti_cheat_enabled=info.vac_enabled,
        players_online=info.player_count,
        players_max=info.max_players,
        player_list=player_names(players),
        game=info.game or None,
        app_id=info.game_id or info.app_id or None,
        folder=info.folder or None,
        protocol=info.protocol,
        bot_count=info.bot_count,
        server_type=info.server_type,
        platform=info.platform,
        keywords=info.keywords or None,
        rules=rules or None,
    )
