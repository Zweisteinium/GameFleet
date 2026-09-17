"""Works out which modpack a Minecraft server runs, without the user maintaining anything.

The source is the container's environment: the itzg/minecraft-server image installs packs from variables that
name them (a Modrinth or CurseForge project, an FTB id, GTNH, or an archive whose file name carries the name).
A name or slug is then looked up on Modrinth for the proper title, icon and link. Servers with hand-installed
mods name no pack anywhere; those can be given a name in the server form.
"""
import asyncio
import logging
import re
import time
from dataclasses import dataclass, replace
from importlib.metadata import version as package_version
from pathlib import PurePosixPath
from typing import Optional
from urllib.parse import urlparse

import aiohttp

log = logging.getLogger(__name__)

MODRINTH_API = "https://api.modrinth.com/v2"
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=10)
LOOKUP_MAX_AGE = 24 * 3600  # seconds a Modrinth answer (or "not found") is reused
LOOKUP_RETRY_AFTER = 300  # seconds before a failed request is tried again


@dataclass(frozen=True)
class Modpack:
    name: str
    # modrinth / curseforge / ftb / official (the pack's own site) / file (named after an archive) / manual
    source: str
    version: Optional[str] = None
    url: Optional[str] = None
    icon: Optional[str] = None
    # Modrinth project slug or id when the environment names one.
    modrinth_id: Optional[str] = None


# ---- environment of itzg/minecraft-server -----------------------------------------------------------------

ARCHIVE = re.compile(r"\.(zip|mrpack|tar\.gz|tgz)$", re.I)
TRAILING_VERSION = re.compile(r"[-_ ]+v?(\d+(?:\.\d+)+[\w.+-]*)$", re.I)
SERVER_WORDS = re.compile(r"[-_ ]*\b(server[-_ ]?(pack|files)?|serverpack|serverfiles)\b[-_ ]*", re.I)


def from_filename(path: str) -> Optional[Modpack]:
    """"Create-Into-the-Sky-v1.2[PATCHED].zip" -> Create Into the Sky, 1.2"""
    stem = ARCHIVE.sub("", PurePosixPath(urlparse(path).path or path).name)
    stem = re.sub(r"[\[(][^\])]*[\])]", "", stem)  # [PATCHED], (server)
    stem = SERVER_WORDS.sub(" ", stem).strip(" -_.")
    version = None
    if match := TRAILING_VERSION.search(stem):
        version, stem = match.group(1), stem[:match.start()]
    name = re.sub(r"[-_.]+", " ", stem).strip()
    return Modpack(name=name, version=version, source="file") if len(name) >= 3 else None


def _title(slug: str) -> str:
    """Readable stand-in until (or unless) Modrinth supplies the real title."""
    return " ".join(word.capitalize() for word in re.split(r"[-_]+", slug) if word)


def from_env(env: dict[str, str]) -> Optional[Modpack]:
    """The pack the container was told to install, from the image's own variables."""
    get = lambda key: (env.get(key) or "").strip()  # noqa: E731
    platform = (get("MODPACK_PLATFORM") or get("MOD_PLATFORM") or get("TYPE")).upper()

    if platform == "GTNH":
        version = get("GTNH_PACK_VERSION")
        return Modpack(name="GregTech: New Horizons", source="official", url="https://www.gtnewhorizons.com/",
                       version=version if version and not version.lower().startswith("latest") else None)

    if platform == "MODRINTH" and (pack := get("MODRINTH_MODPACK")):
        if pack.startswith("/") or ARCHIVE.search(pack) and "modrinth.com" not in pack:
            return from_filename(pack)
        version = get("MODRINTH_VERSION") or None
        if "modrinth.com" in pack:  # https://modrinth.com/modpack/<slug>[/version/<version>]
            parts = [p for p in urlparse(pack).path.split("/") if p]
            pack = parts[1] if len(parts) > 1 else pack
            version = version or (parts[3] if len(parts) > 3 and parts[2] == "version" else None)
        return Modpack(name=_title(pack), source="modrinth", version=version, modrinth_id=pack,
                       url=f"https://modrinth.com/modpack/{pack}")

    if platform == "AUTO_CURSEFORGE":
        slug = get("CF_SLUG")
        if page := get("CF_PAGE_URL"):  # https://www.curseforge.com/minecraft/modpacks/<slug>[/files/<id>]
            parts = [p for p in urlparse(page).path.split("/") if p]
            slug = parts[2] if len(parts) > 2 and parts[1] == "modpacks" else slug
        if slug and slug.lower() != "custom":
            return Modpack(name=_title(slug), source="curseforge", version=get("CF_FILENAME_MATCHER") or None,
                           url=f"https://www.curseforge.com/minecraft/modpacks/{slug}")
        if archive := get("CF_MODPACK_ZIP"):
            return from_filename(archive)
        return None

    if platform in ("FTBA", "FTB") and (pack_id := get("FTB_MODPACK_ID")):
        return Modpack(name=f"FTB modpack {pack_id}", source="ftb", url=f"https://www.feed-the-beast.com/modpacks/{pack_id}")

    for key in ("GENERIC_PACK", "GENERIC_PACKS", "MODPACK", "CF_MODPACK_ZIP"):
        if value := get(key):
            return from_filename(value.split(",")[0].strip())
    return None


# ---- Modrinth ---------------------------------------------------------------------------------------------

def _normal(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


class ModrinthLookup:
    """Project by slug, or a modpack by exact title. Answers are cached, failures are retried later."""

    def __init__(self):
        self._cache: dict[str, tuple[float, Optional[dict]]] = {}
        self._lock = asyncio.Lock()

    async def _get(self, path: str, params: Optional[dict] = None) -> Optional[dict | list]:
        headers = {"User-Agent": f"GameFleet/{package_version('gamefleet-backend')} (github.com/H3xaChad/GameFleet)"}
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
            async with session.get(MODRINTH_API + path, params=params, headers=headers) as response:
                if response.status == 404:
                    return None
                response.raise_for_status()
                return await response.json()

    async def _cached(self, key: str, fetch) -> Optional[dict]:
        async with self._lock:
            hit = self._cache.get(key)
            if hit and time.monotonic() < hit[0]:
                return hit[1]
            try:
                result = await fetch()
                self._cache[key] = (time.monotonic() + LOOKUP_MAX_AGE, result)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
                log.warning("Modrinth lookup %s failed: %s", key, exc)
                result = hit[1] if hit else None
                self._cache[key] = (time.monotonic() + LOOKUP_RETRY_AFTER, result)
            return result

    async def project(self, slug_or_id: str) -> Optional[dict]:
        return await self._cached(f"project:{slug_or_id}", lambda: self._get(f"/project/{slug_or_id}"))

    async def modpack_named(self, name: str) -> Optional[dict]:
        async def search() -> Optional[dict]:
            found = await self._get("/search", {"query": name, "limit": "5", "facets": '[["project_type:modpack"]]'})
            # Only an exact title counts: a near miss would link somebody else's pack.
            return next((hit for hit in (found or {}).get("hits", []) if _normal(hit.get("title", "")) == _normal(name)), None)
        return await self._cached(f"search:{_normal(name)}", search)


modrinth = ModrinthLookup()

FIELDS = ("modpack_name", "modpack_version", "modpack_url", "modpack_icon", "modpack_source")


def as_fields(pack: Optional[Modpack]) -> dict[str, Optional[str]]:
    """The GameServer columns for a pack (all None for no pack)."""
    if pack is None:
        return dict.fromkeys(FIELDS)
    return {"modpack_name": pack.name[:200], "modpack_version": pack.version and pack.version[:100],
            "modpack_url": pack.url, "modpack_icon": pack.icon, "modpack_source": pack.source}


async def manual_fields(name: Optional[str], url: Optional[str]) -> dict[str, Optional[str]]:
    """Columns for what the user typed: a name (linked through Modrinth when no URL is given), or nothing,
    which hands the server back to detection."""
    name, url = (name or "").strip(), (url or "").strip()
    if not name:
        return as_fields(None)
    return as_fields(await resolve(Modpack(name=name, url=url or None, source="manual")))


async def resolve(pack: Modpack) -> Modpack:
    """Add Modrinth's title, icon and link where the pack can be found there for certain."""
    if pack.modrinth_id:
        project = await modrinth.project(pack.modrinth_id)
    elif pack.source in ("file", "manual") and not pack.url:
        project = await modrinth.modpack_named(pack.name)
    else:
        project = None
    if not project:
        return pack
    slug = project.get("slug") or pack.modrinth_id
    return replace(
        pack,
        name=pack.name if pack.source == "manual" else project.get("title") or pack.name,
        url=f"https://modrinth.com/modpack/{slug}",
        icon=project.get("icon_url") or None,
        source="manual" if pack.source == "manual" else "modrinth",
    )
