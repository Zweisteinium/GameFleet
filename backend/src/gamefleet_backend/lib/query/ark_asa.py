"""ARK: Survival Ascended.

ASA does not answer A2S queries; servers register with Epic Online Services (EOS). Public servers
(official and Nitrado/unofficial) are listed on ARK's CDN, which gives us the EOS session id that can
be read directly from the EOS matchmaking API. Servers that are not listed there can still be checked
through RCON (ListPlayers) if credentials are configured.
"""
import asyncio
import base64
import socket
import time
from typing import Any, Optional

import aiohttp

from gamefleet_backend.models.server_info import ArkServerInfo, ServerStatus
from .common import info_from_exception
from .rcon import rcon_execute

# OAuth2 client credentials shipped with the ASA game client (same values gamedig uses).
EOS_CLIENT_ID = "xyza7891muomRmynIIHaJB9COBKkwj6n"
EOS_CLIENT_SECRET = "PP5UGxysEieNfSrEicaD1N2Bb3TdXuD7xHYcsdUHZ7s"
EOS_DEPLOYMENT_ID = "ad9a8feffb3b4b2ca315546f038c3ae2"
EOS_API = "https://api.epicgames.dev"

CDN_SERVER_LISTS = [
    "https://cdn2.arkdedicated.com/servers/asa/officialserverlist.json",
    "https://cdn2.arkdedicated.com/servers/asa/unofficialserverlist.json",
]
LIST_CACHE_TTL = 120.0
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=30)

_list_cache: dict[str, tuple[float, list[dict]]] = {}
_list_lock = asyncio.Lock()
_token_cache: tuple[float, str] | None = None


async def _get_access_token(session: aiohttp.ClientSession) -> str:
    global _token_cache
    if _token_cache and _token_cache[0] > time.monotonic():
        return _token_cache[1]
    auth = base64.b64encode(f"{EOS_CLIENT_ID}:{EOS_CLIENT_SECRET}".encode()).decode()
    async with session.post(
        f"{EOS_API}/auth/v1/oauth/token",
        data={"grant_type": "client_credentials", "deployment_id": EOS_DEPLOYMENT_ID},
        headers={"Authorization": f"Basic {auth}"},
    ) as response:
        response.raise_for_status()
        data = await response.json()
    _token_cache = (time.monotonic() + max(60, int(data.get("expires_in", 3600)) - 60), data["access_token"])
    return data["access_token"]


async def _get_server_list(session: aiohttp.ClientSession, url: str) -> list[dict]:
    async with _list_lock:
        cached = _list_cache.get(url)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        async with session.get(url) as response:
            response.raise_for_status()
            servers = await response.json(content_type=None)
        _list_cache[url] = (time.monotonic() + LIST_CACHE_TTL, servers)
        return servers


async def _find_session_id(session: aiohttp.ClientSession, address: str, port: int) -> Optional[str]:
    ip = await asyncio.get_running_loop().run_in_executor(None, socket.gethostbyname, address)
    for url in CDN_SERVER_LISTS:
        for server in await _get_server_list(session, url):
            if server.get("IP") == ip and server.get("Port") == port:
                return server.get("SessionID")
    return None


async def _get_session(session: aiohttp.ClientSession, session_id: str) -> dict[str, Any]:
    token = await _get_access_token(session)
    url = f"{EOS_API}/wildcard/matchmaking/v1/{EOS_DEPLOYMENT_ID}/sessions/{session_id}"
    async with session.get(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}) as response:
        response.raise_for_status()
        return (await response.json())["publicData"]


def _info_from_eos(data: dict[str, Any]) -> ArkServerInfo:
    attributes = data.get("attributes", {})
    settings = data.get("settings", {})
    build = attributes.get("BUILDID_s")
    minor = attributes.get("MINORBUILDID_s")
    mod_ids = [m for m in (attributes.get("ENABLEDMODS_s") or "").split(",") if m]
    pve = attributes.get("SESSIONISPVE_l")
    return ArkServerInfo(
        status=ServerStatus.ONLINE,
        version=f"{build}.{minor}" if build else None,
        server_name=attributes.get("CUSTOMSERVERNAME_s") or attributes.get("SESSIONNAME_s"),
        map_name=attributes.get("FRIENDLYMAPNAME_s") or attributes.get("MAPNAME_s"),
        password_protected=attributes.get("SERVERPASSWORD_b"),
        anti_cheat_enabled=attributes.get("SERVERUSESBATTLEYE_b"),
        players_online=data.get("totalPlayers"),
        players_max=settings.get("maxPublicPlayers"),
        player_list=[p["name"] for p in data.get("publicPlayers", []) if p.get("name")] or None,
        # ASA mods are CurseForge projects; the project URL redirects to the mod page.
        mods=[{"id": mod_id, "url": f"https://www.curseforge.com/projects/{mod_id}"} for mod_id in mod_ids] or None,
        game_mode=None if pve is None else ("PvE" if pve else "PvP"),
        day_time=attributes.get("DAYTIME_s"),
        official=attributes.get("OFFICIALSERVER_s") == "1",
        pve=None if pve is None else bool(pve),
        cluster_id=attributes.get("CLUSTERID_s") or None,
        platform_type=attributes.get("SERVERPLATFORMTYPE_s"),
    )


async def _info_from_rcon(address: str, rcon_port: int, rcon_password: str) -> ArkServerInfo:
    (players_output,) = await rcon_execute(address, rcon_port, rcon_password, ["ListPlayers"])
    # Format: "0. PlayerName, 0002xxxxxxxxxxxx" per line, or "No Players Connected".
    players = []
    for line in players_output.splitlines():
        line = line.strip()
        if line and line[0].isdigit() and ". " in line:
            players.append(line.split(". ", 1)[1].rsplit(",", 1)[0].strip())
    return ArkServerInfo(status=ServerStatus.ONLINE, players_online=len(players), player_list=players or None)


async def get_ark_asa_server_info(
    address: str,
    port: int = 7777,
    rcon_port: Optional[int] = None,
    rcon_password: Optional[str] = None,
) -> ArkServerInfo:
    try:
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
            session_id = await _find_session_id(session, address, port)
            if session_id:
                return _info_from_eos(await _get_session(session, session_id))
    except Exception as exc:
        if not rcon_password:
            return ArkServerInfo(status=ServerStatus.UNKNOWN, error_message=f"EOS lookup failed: {exc}")

    if rcon_password:
        try:
            return await _info_from_rcon(address, rcon_port or 27020, rcon_password)
        except Exception as exc:
            return info_from_exception(ArkServerInfo, exc)

    return ArkServerInfo(
        status=ServerStatus.UNKNOWN,
        error_message="Server not found in ARK's public server lists. Configure RCON to monitor private servers.",
    )
