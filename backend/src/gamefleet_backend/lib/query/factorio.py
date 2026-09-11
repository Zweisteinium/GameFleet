"""Factorio has no public query protocol, so live info is read through RCON (enable it with --rcon-port/--rcon-password)."""
import re
from typing import Optional

from gamefleet_backend.models.server_info import FactorioServerInfo, ServerStatus
from .common import info_from_exception
from .rcon import rcon_execute

COMMANDS = [
    "/version",
    "/players online",
    "/config get name",
    "/config get description",
    "/config get max-players",
    "/config get tags",
    "/config get visibility-public",
    "/config get require-user-verification",
    "/config get allow-commands",
    "/time",
    "/evolution",
    "/seed",
]

EVOLUTION_RE = re.compile(r"^(.+?) - Evolution factor: (\d+\.\d+)", re.MULTILINE)


def _after_colon(text: str) -> str:
    """'Server name: Foo' -> 'Foo'; also strips a trailing period."""
    _, _, value = text.strip().partition(":")
    return value.strip().rstrip(".")


def _flag(text: str) -> Optional[bool]:
    value = _after_colon(text).lower()
    return True if value == "true" else False if value == "false" else None


def _players(text: str) -> list[str]:
    # "Online players (2):\n  Alice (online)\n  Bob (online)"
    names = []
    for line in text.splitlines()[1:]:
        name = line.strip().removesuffix("(online)").strip()
        if name:
            names.append(name)
    return names


async def get_factorio_server_info(
    address: str,
    port: int = 34197,
    rcon_port: Optional[int] = None,
    rcon_password: Optional[str] = None,
) -> FactorioServerInfo:
    if not rcon_password:
        return FactorioServerInfo(
            status=ServerStatus.UNKNOWN,
            error_message="Factorio needs RCON: set the server's RCON port and password.",
        )
    try:
        (version, players, name, description, max_players, tags,
         public, verification, commands, game_time, evolution, seed) = await rcon_execute(
            address, rcon_port or 27015, rcon_password, COMMANDS
        )
    except Exception as exc:
        return info_from_exception(FactorioServerInfo, exc)

    player_list = _players(players)
    max_players_value = int(max_players.strip() or 0) if max_players.strip().isdigit() else 0
    tag_list = [t.strip() for t in _after_colon(tags).split(",") if t.strip()]

    return FactorioServerInfo(
        status=ServerStatus.ONLINE,
        version=version.strip() or None,
        server_name=_after_colon(name) or None,
        description=_after_colon(description) or None,
        players_online=len(player_list),
        players_max=max_players_value or None,  # 0 means unlimited
        player_list=player_list or None,
        tags=tag_list or None,
        public=_flag(public),
        require_user_verification=_flag(verification),
        allow_commands=_after_colon(commands) or None,
        game_time=game_time.strip() or None,
        evolution={surface: float(value) for surface, value in EVOLUTION_RE.findall(evolution)} or None,
        seed=seed.strip() or None,
    )
