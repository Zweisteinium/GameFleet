"""Downloads game artwork (poster + hero banner) once and serves it from a local disk cache."""
import asyncio
import os
import time
from pathlib import Path
from typing import Optional

import aiohttp

from gamefleet_backend.models.game_server_type import GameServerType

STEAM_CDN = "https://cdn.cloudflare.steamstatic.com/steam/apps"

# Steam app ids for games that are on Steam; artwork is fetched from the Steam CDN.
STEAM_APP_IDS: dict[GameServerType, int] = {
    GameServerType.factorio: 427520,
    GameServerType.satisfactory: 526870,
    GameServerType.ark_ase: 346110,
    GameServerType.ark_asa: 2399830,
    GameServerType.valheim: 892970,
    GameServerType.rust: 252490,
    GameServerType.seven_days_to_die: 251570,
    GameServerType.palworld: 1623730,
    GameServerType.project_zomboid: 108600,
    GameServerType.enshrouded: 1203620,
    GameServerType.v_rising: 1604030,
    GameServerType.conan_exiles: 440900,
    GameServerType.dayz: 221100,
    GameServerType.counter_strike: 730,
    GameServerType.team_fortress_2: 440,
    GameServerType.garrys_mod: 4000,
    GameServerType.unturned: 304930,
}

# Games without a Steam page get explicit URLs; anything missing here has no artwork (frontend shows a fallback).
CUSTOM_ASSETS: dict[GameServerType, dict[str, str]] = {
    GameServerType.minecraft: {
        "poster": "https://minecraft.wiki/images/Grass_Block_JE7_BE6.png",
        "hero": "https://minecraft.wiki/images/Trails_%26_Tales_key_art.jpg",
    },
    GameServerType.minecraft_bedrock: {
        "poster": "https://minecraft.wiki/images/Bedrock_JE2_BE2.png",
        "hero": "https://minecraft.wiki/images/Trails_%26_Tales_key_art.jpg",
    },
}

ASSET_KINDS = {"poster": "library_600x900.jpg", "hero": "library_hero.jpg"}
CACHE_DIR = Path(os.getenv("ASSET_CACHE_DIR", "data/assets"))
RETRY_FAILED_AFTER = 3600  # seconds before a failed download is attempted again
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=20)

_failed: dict[str, float] = {}
_locks: dict[str, asyncio.Lock] = {}


def asset_url(game: GameServerType, kind: str) -> Optional[str]:
    if game in CUSTOM_ASSETS:
        return CUSTOM_ASSETS[game].get(kind)
    app_id = STEAM_APP_IDS.get(game)
    if app_id and kind in ASSET_KINDS:
        return f"{STEAM_CDN}/{app_id}/{ASSET_KINDS[kind]}"
    return None


async def get_asset_path(game: GameServerType, kind: str) -> Optional[Path]:
    """Return the cached file for this game/kind, downloading it on first use. None if unavailable."""
    url = asset_url(game, kind)
    if url is None:
        return None

    extension = ".png" if url.lower().endswith(".png") else ".jpg"
    path = CACHE_DIR / f"{game.value}_{kind}{extension}"
    if path.exists():
        return path

    key = str(path)
    if _failed.get(key, 0) > time.monotonic():
        return None

    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        if path.exists():
            return path
        try:
            async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
                async with session.get(url, headers={"User-Agent": "GameFleet/0.3"}) as response:
                    response.raise_for_status()
                    data = await response.read()
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".part")
            tmp.write_bytes(data)
            tmp.replace(path)
            return path
        except Exception:
            _failed[key] = time.monotonic() + RETRY_FAILED_AFTER
            return None
