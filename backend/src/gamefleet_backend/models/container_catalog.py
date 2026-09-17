"""Fingerprints for recognising game servers that run as Docker containers on this host.

Detection reads the container as it is (GameFleet defines no labels), most reliable first:

1. Known images (IMAGE_CATALOG) identify the game *and* tell us where its data lives and how its RCON
   password is configured, so the import needs no user input.
2. Keywords in the image or container name give a suggestion that the user confirms.
3. Exposed ports only confirm or rank the above; on their own they are too ambiguous (7777 is ARK,
   Satisfactory, Terraria, ...), so a port-only match is shown but never auto-imported.
"""
import re
from dataclasses import dataclass, field
from typing import Optional

from gamefleet_backend.models.game_server_type import GameServerType

@dataclass(frozen=True)
class ImageFingerprint:
    game: GameServerType
    # Path of the persistent data (usually the volume mount) and of the world/save files inside it.
    data_path: Optional[str] = None
    world_path: Optional[str] = None
    # How the image is normally told its RCON password: an environment variable and/or a file.
    rcon_password_env: Optional[str] = None
    rcon_password_file: Optional[str] = None
    # Container-side ports when the image deviates from the game's defaults.
    port: Optional[int] = None
    query_port: Optional[int] = None
    rcon_port: Optional[int] = None
    aliases: tuple[str, ...] = field(default_factory=tuple)


# Keyed by image repository without registry, tag or digest (``itzg/minecraft-server``).
IMAGE_CATALOG: dict[str, ImageFingerprint] = {
    "itzg/minecraft-server": ImageFingerprint(
        GameServerType.minecraft, "/data", "/data/world", rcon_password_env="RCON_PASSWORD", rcon_port=25575
    ),
    "itzg/minecraft-bedrock-server": ImageFingerprint(GameServerType.minecraft_bedrock, "/data", "/data/worlds"),
    "marctv/minecraft-papermc-server": ImageFingerprint(GameServerType.minecraft, "/data", "/data/world"),
    "factoriotools/factorio": ImageFingerprint(
        GameServerType.factorio, "/factorio", "/factorio/saves",
        rcon_password_file="/factorio/config/rconpw", rcon_port=27015,
    ),
    "wolveix/satisfactory-server": ImageFingerprint(GameServerType.satisfactory, "/config", "/config/saved"),
    "lloesche/valheim-server": ImageFingerprint(GameServerType.valheim, "/config", "/config/worlds_local"),
    "mbround18/valheim": ImageFingerprint(
        GameServerType.valheim,
        "/home/steam/.config/unity3d/IronGate/Valheim", "/home/steam/.config/unity3d/IronGate/Valheim/worlds_local",
    ),
    "thijsvanloef/palworld-server-docker": ImageFingerprint(
        GameServerType.palworld, "/palworld", "/palworld/Pal/Saved", rcon_password_env="ADMIN_PASSWORD", rcon_port=25575
    ),
    "didstopia/rust-server": ImageFingerprint(
        GameServerType.rust, "/steamcmd/rust", "/steamcmd/rust/server", rcon_password_env="RUST_RCON_PASSWORD", rcon_port=28016
    ),
    "vinanrra/7dtd-server": ImageFingerprint(GameServerType.seven_days_to_die, "/home/sdtdserver", "/home/sdtdserver/Saves"),
    "mornedhels/enshrouded-server": ImageFingerprint(GameServerType.enshrouded, "/opt/enshrouded", "/opt/enshrouded/savegame"),
    "sknnr/enshrouded-dedicated-server": ImageFingerprint(GameServerType.enshrouded, "/home/steam/enshrouded/savegame"),
    "trueosiris/vrising": ImageFingerprint(GameServerType.v_rising, "/mnt/vrising/persistentdata", "/mnt/vrising/persistentdata/Saves"),
    "thmhoag/arkserver": ImageFingerprint(GameServerType.ark_ase, "/ark", "/ark/server/ShooterGame/Saved"),
    "acekorneya/asa_server": ImageFingerprint(GameServerType.ark_asa, "/home/pok/arkserver", "/home/pok/arkserver/ShooterGame/Saved"),
    "mschnitzer/asa-linux-server": ImageFingerprint(GameServerType.ark_asa, "/home/gameserver/server-files", "/home/gameserver/server-files/ShooterGame/Saved"),
    "cm2network/tf2": ImageFingerprint(GameServerType.team_fortress_2, "/home/steam/tf-dedicated"),
    "cm2network/csgo": ImageFingerprint(GameServerType.counter_strike, "/home/steam/csgo-dedicated"),
    "cm2network/cs2": ImageFingerprint(GameServerType.counter_strike, "/home/steam/cs2-dedicated"),
    "joedwards32/cs2": ImageFingerprint(GameServerType.counter_strike, "/home/steam/cs2-dedicated"),
    "cm2network/gmod": ImageFingerprint(GameServerType.garrys_mod, "/home/steam/gmod-dedicated"),
    "ceifa/garrysmod": ImageFingerprint(GameServerType.garrys_mod, "/home/gmod/server/garrysmod", "/home/gmod/server/garrysmod/data"),
    "cm2network/steamcmd": ImageFingerprint(GameServerType.steam),
    "danixu86/project-zomboid-dedicated-server": ImageFingerprint(GameServerType.project_zomboid, "/server-data", "/server-data/Saves"),
    "afey/zomboid": ImageFingerprint(GameServerType.project_zomboid, "/home/steam/Zomboid", "/home/steam/Zomboid/Saves"),
    "alinmear/docker-conanexiles": ImageFingerprint(GameServerType.conan_exiles, "/conanexiles", "/conanexiles/ConanSandbox/Saved"),
}

# Ordered: the first matching keyword wins, so more specific names come first.
KEYWORDS: list[tuple[re.Pattern[str], GameServerType]] = [
    (re.compile(r"bedrock", re.I), GameServerType.minecraft_bedrock),
    (re.compile(r"minecraft|papermc|spigot|purpur|fabric|forge|paper-?server|velocity", re.I), GameServerType.minecraft),
    (re.compile(r"factorio", re.I), GameServerType.factorio),
    (re.compile(r"satisfactory", re.I), GameServerType.satisfactory),
    (re.compile(r"ark.*(asa|ascended)|asa[-_]?server", re.I), GameServerType.ark_asa),
    (re.compile(r"\bark\b|arkserver|ark[-_]server|survival[-_]?evolved", re.I), GameServerType.ark_ase),
    (re.compile(r"valheim", re.I), GameServerType.valheim),
    (re.compile(r"\brust\b|rust[-_]?server", re.I), GameServerType.rust),
    (re.compile(r"7dtd|7days|sdtd|seven[-_]?days", re.I), GameServerType.seven_days_to_die),
    (re.compile(r"palworld", re.I), GameServerType.palworld),
    (re.compile(r"zomboid", re.I), GameServerType.project_zomboid),
    (re.compile(r"enshrouded", re.I), GameServerType.enshrouded),
    (re.compile(r"v-?rising", re.I), GameServerType.v_rising),
    (re.compile(r"conan", re.I), GameServerType.conan_exiles),
    (re.compile(r"dayz", re.I), GameServerType.dayz),
    (re.compile(r"cs2|csgo|counter-?strike|cstrike", re.I), GameServerType.counter_strike),
    (re.compile(r"\btf2\b|team-?fortress", re.I), GameServerType.team_fortress_2),
    (re.compile(r"gmod|garry", re.I), GameServerType.garrys_mod),
    (re.compile(r"unturned", re.I), GameServerType.unturned),
    (re.compile(r"steamcmd|srcds", re.I), GameServerType.steam),
]

# Images that are never game servers even if a keyword matches (databases, proxies, GameFleet itself).
NEVER = re.compile(r"postgres|mysql|mariadb|redis|nginx|traefik|caddy|gamefleet|portainer|watchtower|hello-world", re.I)


def normalize_image(reference: str) -> str:
    """'ghcr.io/itzg/minecraft-server:java21@sha256:...' -> 'itzg/minecraft-server'."""
    ref = reference.split("@", 1)[0]
    # Strip the tag, but not a registry port ("localhost:5000/repo").
    head, sep, tail = ref.rpartition(":")
    if sep and "/" not in tail:
        ref = head
    parts = ref.split("/")
    if len(parts) > 2 or (len(parts) == 2 and ("." in parts[0] or ":" in parts[0] or parts[0] == "localhost")):
        parts = parts[1:]  # drop the registry host
    if len(parts) == 1:
        parts = ["library", parts[0]]
    return "/".join(parts[-2:]).lower()


def lookup_image(reference: str) -> Optional[ImageFingerprint]:
    repo = normalize_image(reference)
    if repo in IMAGE_CATALOG:
        return IMAGE_CATALOG[repo]
    for fingerprint in IMAGE_CATALOG.values():
        if repo in fingerprint.aliases:
            return fingerprint
    return None


def lookup_keyword(*texts: str) -> Optional[GameServerType]:
    haystack = " ".join(t for t in texts if t)
    if NEVER.search(haystack):
        return None
    for pattern, game in KEYWORDS:
        if pattern.search(haystack):
            return game
    return None
