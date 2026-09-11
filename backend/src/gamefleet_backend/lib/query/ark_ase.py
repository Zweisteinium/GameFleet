"""ARK: Survival Evolved - queried through A2S on the server's query port (default 27015)."""
import re

from gamefleet_backend.models.server_info import ArkServerInfo, ServerStatus
from .common import info_from_exception
from .steam import query_a2s, player_names, clean_text

VERSION_RE = re.compile(r"\(v([\d.]+)\)\s*$")
MOD_KEY_RE = re.compile(r"^MOD(\d+)_s$")


def _flag(rules: dict, key: str) -> bool | None:
    value = rules.get(key)
    if value is None:
        return None
    return value.lower() in ("1", "true")


async def get_ark_ase_server_info(address: str, query_port: int = 27015) -> ArkServerInfo:
    try:
        info, rules, players = await query_a2s(address, query_port)
    except Exception as exc:
        return info_from_exception(ArkServerInfo, exc)

    rules = rules or {}
    server_name = clean_text(info.server_name) or ""
    version_match = VERSION_RE.search(server_name)
    mods = [
        {"id": mod_id, "url": f"https://steamcommunity.com/sharedfiles/filedetails/?id={mod_id}"}
        for key, value in sorted(rules.items())
        if MOD_KEY_RE.match(key) and (mod_id := value.split(":")[0])
    ]

    return ArkServerInfo(
        status=ServerStatus.ONLINE,
        latency=info.ping * 1000,
        version=version_match.group(1) if version_match else (info.version or None),
        server_name=VERSION_RE.sub("", server_name).strip(" -") or None,
        map_name=info.map_name or None,
        password_protected=_flag(rules, "ServerPassword_b") if "ServerPassword_b" in rules else info.password_protected,
        anti_cheat_enabled=_flag(rules, "SERVERUSESBATTLEYE_b"),
        players_online=info.player_count,
        players_max=info.max_players,
        player_list=player_names(players),
        mods=mods or None,
        game_mode="PvE" if _flag(rules, "SESSIONISPVE_i") else ("PvP" if "SESSIONISPVE_i" in rules else None),
        day_time=rules.get("DayTime_s"),
        official=_flag(rules, "OFFICIALSERVER_i"),
        pve=_flag(rules, "SESSIONISPVE_i"),
        cluster_id=rules.get("ClusterId_s") or None,
    )
