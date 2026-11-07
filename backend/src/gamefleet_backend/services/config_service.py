"""Settings of a Docker-linked server: the important keys of its main settings file as a form, plus the
known text files (whitelists, ban lists, engine configs) for a raw editor.

Each game has a ConfigLayout naming its settings file and the files it may expose; the endpoints only accept
paths from that list, never arbitrary ones. Files are read and written through Docker's archive endpoint, so
it works while the server is stopped; a write lands next to the file as `<name>.gamefleet-tmp` and is moved
into place by a short shell with the previous owner and mode, so the game's user keeps its file.
"""
import io
import json
import logging
import posixpath
import re
import tarfile
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import docker.errors

from gamefleet_backend.db.models.game_server import GameServer
from gamefleet_backend.models.config_info import (
    ConfigFile, ConfigInfo, FileContent, FileWritten, SettingScalar, SettingSpec, SettingValue,
)
from gamefleet_backend.models.game_server_type import GameServerType
from gamefleet_backend.services.docker_service import docker_service

log = logging.getLogger(__name__)

MAX_FILE = 1 << 20  # bytes a raw file may have to be edited in the browser


class ConfigError(Exception):
    """A problem the user can act on; the message is shown as is."""


@dataclass(frozen=True)
class ConfigLayout:
    settings_file: Optional[str] = None  # {data} and {world} as in backup_service
    format: Optional[str] = None  # "properties" | "json" | "ini" (keys as "<section>/<key>")
    specs: tuple[SettingSpec, ...] = ()
    env_map: dict[str, str] = field(default_factory=dict)  # setting key -> container variable overriding it
    files: tuple[tuple[str, str], ...] = ()  # (path template, label)
    # Keys fixed once the world exists; the world folder is `{data}/<world_dir>` with the named key's value.
    world_keys: tuple[str, ...] = ()
    world_dir: str = "{data}/{name}"
    world_name_key: str = ""
    # Set when the game rewrites its settings files while running or on shutdown (ARK): edits wait for a stop.
    edit_when_stopped: str = ""


def _s(key: str, label: str, type: str, description: str = "", options: tuple[str, ...] = (), group: str = "") -> SettingSpec:
    return SettingSpec(key=key, label=label, type=type, description=description, options=list(options), group=group)


MINECRAFT_SPECS = (
    _s("motd", "MOTD", "str", "Shown under the server name in the multiplayer list.", group="General"),
    _s("max-players", "Max players", "int", group="General"),
    _s("difficulty", "Difficulty", "enum", options=("peaceful", "easy", "normal", "hard"), group="Gameplay"),
    _s("gamemode", "Game mode", "enum", "Mode for new players.", ("survival", "creative", "adventure", "spectator"), "Gameplay"),
    _s("hardcore", "Hardcore", "bool", "Death bans the player; forces hard difficulty.", group="Gameplay"),
    _s("pvp", "PvP", "bool", group="Gameplay"),
    _s("allow-flight", "Allow flight", "bool", "Otherwise players in survival who fly are kicked.", group="Gameplay"),
    _s("allow-nether", "Allow Nether", "bool", group="Gameplay"),
    _s("enable-command-block", "Command blocks", "bool", group="Gameplay"),
    _s("spawn-protection", "Spawn protection", "int", "Radius in blocks that only ops can change; 0 disables.", group="Gameplay"),
    _s("online-mode", "Online mode", "bool", "Verify players with Mojang; off allows offline accounts.", group="Access"),
    _s("white-list", "Whitelist", "bool", "Only players in whitelist.json may join.", group="Access"),
    _s("enforce-whitelist", "Enforce whitelist", "bool", "Kick players removed from the whitelist.", group="Access"),
    _s("view-distance", "View distance", "int", "Chunks sent to each player; the main performance knob.", group="Performance"),
    _s("simulation-distance", "Simulation distance", "int", "Chunks around players that tick.", group="Performance"),
    _s("level-name", "World folder", "str", group="World"),
    _s("level-seed", "Seed", "str", group="World"),
)
MINECRAFT_ENV = {
    "motd": "MOTD", "max-players": "MAX_PLAYERS", "difficulty": "DIFFICULTY", "gamemode": "MODE", "pvp": "PVP",
    "online-mode": "ONLINE_MODE", "white-list": "ENABLE_WHITELIST", "enforce-whitelist": "ENFORCE_WHITELIST",
    "view-distance": "VIEW_DISTANCE", "simulation-distance": "SIMULATION_DISTANCE", "spawn-protection": "SPAWN_PROTECTION",
    "allow-flight": "ALLOW_FLIGHT", "hardcore": "HARDCORE", "level-seed": "SEED", "level-name": "LEVEL",
    "enable-command-block": "ENABLE_COMMAND_BLOCK", "allow-nether": "ALLOW_NETHER",
}
BEDROCK_SPECS = (
    _s("server-name", "Server name", "str", group="General"),
    _s("max-players", "Max players", "int", group="General"),
    _s("gamemode", "Game mode", "enum", options=("survival", "creative", "adventure"), group="Gameplay"),
    _s("difficulty", "Difficulty", "enum", options=("peaceful", "easy", "normal", "hard"), group="Gameplay"),
    _s("allow-cheats", "Allow cheats", "bool", "Commands such as /give for players.", group="Gameplay"),
    _s("online-mode", "Online mode", "bool", "Require Xbox Live accounts.", group="Access"),
    _s("allow-list", "Allow list", "bool", "Only players in allowlist.json may join.", group="Access"),
    _s("default-player-permission-level", "Default permission", "enum", options=("visitor", "member", "operator"), group="Access"),
    _s("view-distance", "View distance", "int", group="Performance"),
    _s("level-name", "World folder", "str", group="World"),
)
BEDROCK_ENV = {
    "server-name": "SERVER_NAME", "gamemode": "GAMEMODE", "difficulty": "DIFFICULTY", "max-players": "MAX_PLAYERS",
    "online-mode": "ONLINE_MODE", "allow-cheats": "ALLOW_CHEATS", "level-name": "LEVEL_NAME", "view-distance": "VIEW_DISTANCE",
    "allow-list": "ALLOW_LIST", "default-player-permission-level": "DEFAULT_PLAYER_PERMISSION_LEVEL",
}
FACTORIO_SPECS = (
    _s("name", "Server name", "str", group="General"),
    _s("description", "Description", "str", group="General"),
    _s("tags", "Tags", "str", "Comma separated.", group="General"),
    _s("max_players", "Max players", "int", "0 means unlimited.", group="General"),
    _s("visibility.public", "Public listing", "bool", "Needs a Factorio account in the settings file.", group="Access"),
    _s("visibility.lan", "LAN listing", "bool", group="Access"),
    _s("game_password", "Game password", "str", group="Access"),
    _s("require_user_verification", "Verified accounts", "bool", "Only players with a valid Factorio account.", group="Access"),
    _s("allow_commands", "Commands", "enum", options=("true", "admins-only", "false"), group="Access"),
    _s("autosave_interval", "Autosave interval", "int", "Minutes.", group="Saving"),
    _s("autosave_slots", "Autosave slots", "int", group="Saving"),
    _s("afk_autokick_interval", "AFK kick", "int", "Minutes; 0 disables.", group="Gameplay"),
    _s("auto_pause", "Pause when empty", "bool", group="Gameplay"),
    _s("only_admins_can_pause_the_game", "Only admins pause", "bool", group="Gameplay"),
)

ARK_INI = "{data}/server/ShooterGame/Saved/Config/LinuxServer"  # /app/*.ini are symlinks into it
ARK_SPECS = (
    _s("SessionSettings/SessionName", "Server name", "str", "Shown in the server browser.", group="General"),
    _s("/Script/Engine.GameSession/MaxPlayers", "Max players", "int", group="General"),
    _s("MessageOfTheDay/Message", "Message of the day", "str", "Shown to players when they join.", group="General"),
    _s("MessageOfTheDay/Duration", "Message duration", "int", "Seconds the message stays on screen.", group="General"),
    _s("ServerSettings/ServerPVE", "PvE", "bool", "Players cannot damage each other or their structures.", group="Gameplay"),
    _s("ServerSettings/DifficultyOffset", "Difficulty offset", "float", "0 to 1; with the official difficulty sets the wild dino levels.", group="Gameplay"),
    _s("ServerSettings/OverrideOfficialDifficulty", "Official difficulty", "float", "5.0 allows wild dinos up to level 150.", group="Gameplay"),
    _s("ServerSettings/AllowThirdPersonPlayer", "Third person", "bool", group="Gameplay"),
    _s("ServerSettings/ServerCrosshair", "Crosshair", "bool", group="Gameplay"),
    _s("ServerSettings/ShowMapPlayerLocation", "Own position on the map", "bool", group="Gameplay"),
    _s("ServerSettings/ShowFloatingDamageText", "Damage numbers", "bool", group="Gameplay"),
    _s("ServerSettings/PreventOfflinePvP", "Offline raid protection", "bool", "Protects tribes whose members are all offline.", group="Gameplay"),
    _s("ServerSettings/XPMultiplier", "XP", "float", group="Rates"),
    _s("ServerSettings/TamingSpeedMultiplier", "Taming speed", "float", group="Rates"),
    _s("ServerSettings/HarvestAmountMultiplier", "Harvest amount", "float", group="Rates"),
    _s("ServerSettings/HarvestHealthMultiplier", "Resource health", "float", "Higher means more hits per tree or rock.", group="Rates"),
    _s("ServerSettings/ResourcesRespawnPeriodMultiplier", "Resource respawn time", "float", "Lower respawns faster.", group="Rates"),
    _s("ServerSettings/ItemStackSizeMultiplier", "Stack size", "float", group="Rates"),
    _s("ServerSettings/DayTimeSpeedScale", "Day speed", "float", group="Rates"),
    _s("ServerSettings/NightTimeSpeedScale", "Night speed", "float", group="Rates"),
    _s("ServerSettings/DinoCountMultiplier", "Wild dino count", "float", group="Rates"),
    _s("ServerSettings/PlayerCharacterFoodDrainMultiplier", "Food drain", "float", group="Rates"),
    _s("ServerSettings/PlayerCharacterWaterDrainMultiplier", "Water drain", "float", group="Rates"),
    _s("ServerSettings/MaxTamedDinos", "Max tamed dinos", "int", "For the whole server.", group="Limits"),
    _s("ServerSettings/KickIdlePlayersPeriod", "Idle kick", "int", "Seconds.", group="Limits"),
    _s("ServerSettings/AutoSavePeriodMinutes", "Autosave interval", "float", "Minutes.", group="Saving"),
    _s("ServerSettings/RCONEnabled", "RCON", "bool", group="Access"),
    _s("ServerSettings/RCONPort", "RCON port", "int", group="Access"),
)
# hermsi/ark-server hands these to arkmanager, which passes them on the command line: they win over the file.
ARK_ENV = {"SessionSettings/SessionName": "SESSION_NAME", "/Script/Engine.GameSession/MaxPlayers": "MAX_PLAYERS"}

LAYOUTS: dict[GameServerType, ConfigLayout] = {
    GameServerType.minecraft: ConfigLayout(
        "{data}/server.properties", "properties", MINECRAFT_SPECS, MINECRAFT_ENV,
        (("{data}/server.properties", "server.properties"), ("{data}/ops.json", "Operators"),
         ("{data}/whitelist.json", "Whitelist"), ("{data}/banned-players.json", "Banned players"),
         ("{data}/banned-ips.json", "Banned IPs"), ("{data}/bukkit.yml", "bukkit.yml"),
         ("{data}/spigot.yml", "spigot.yml"), ("{data}/config/paper-global.yml", "paper-global.yml")),
        world_keys=("level-name", "level-seed"), world_dir="{data}/{name}", world_name_key="level-name",
    ),
    GameServerType.minecraft_bedrock: ConfigLayout(
        "{data}/server.properties", "properties", BEDROCK_SPECS, BEDROCK_ENV,
        (("{data}/server.properties", "server.properties"), ("{data}/allowlist.json", "Allow list"),
         ("{data}/permissions.json", "Permissions")),
        world_keys=("level-name",), world_dir="{data}/worlds/{name}", world_name_key="level-name",
    ),
    GameServerType.factorio: ConfigLayout(
        "{data}/config/server-settings.json", "json", FACTORIO_SPECS, {},
        (("{data}/config/server-settings.json", "server-settings.json"),
         ("{data}/config/map-gen-settings.json", "map-gen-settings.json"),
         ("{data}/config/map-settings.json", "map-settings.json"),
         ("{data}/config/server-adminlist.json", "Admins"), ("{data}/config/server-whitelist.json", "Whitelist"),
         ("{data}/config/server-banlist.json", "Ban list")),
    ),
    GameServerType.ark_ase: ConfigLayout(
        f"{ARK_INI}/GameUserSettings.ini", "ini", ARK_SPECS, ARK_ENV,
        ((f"{ARK_INI}/GameUserSettings.ini", "GameUserSettings.ini"), (f"{ARK_INI}/Game.ini", "Game.ini"),
         ("{data}/crontab", "crontab")),
        edit_when_stopped="ARK writes its .ini files when it shuts down and would undo the change. Stop the server first.",
    ),
    GameServerType.valheim: ConfigLayout(
        files=(("{data}/adminlist.txt", "Admins"), ("{data}/bannedlist.txt", "Banned"), ("{data}/permittedlist.txt", "Permitted")),
    ),
    GameServerType.satisfactory: ConfigLayout(
        files=tuple((f"{{data}}/gamefiles/FactoryGame/Saved/Config/LinuxServer/{name}", name)
                    for name in ("Game.ini", "Engine.ini", "GameUserSettings.ini", "ServerSettings.ini")),
    ),
}


# ---- file formats ------------------------------------------------------------------------------------------

_UNICODE = re.compile(r"\\u([0-9a-fA-F]{4})")


def _unescape(value: str) -> str:
    """Java .properties value: \\uXXXX and the escaped separators."""
    value = _UNICODE.sub(lambda m: chr(int(m.group(1), 16)), value)
    value = value.encode("utf-16", "surrogatepass").decode("utf-16", "replace")  # join surrogate pairs
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t", "r": "\r"}.get(m.group(1), m.group(1)), value)


def _escape(value: str) -> str:
    """The way Minecraft writes values: separators and non-ASCII escaped, so the file survives a reload."""
    out = []
    for ch in value:
        if ch in "\\:=#!":
            out.append("\\" + ch)
        elif ch == "\n":
            out.append("\\n")
        elif ord(ch) > 0xFFFF:  # Java reads \u escapes as UTF-16: a surrogate pair
            high, low = divmod(ord(ch) - 0x10000, 0x400)
            out.append(f"\\u{0xD800 + high:04x}\\u{0xDC00 + low:04x}")
        elif ord(ch) > 126 or ord(ch) < 32:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return "".join(out)


def read_properties(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped[0] in "#!":
            continue
        match = re.match(r"^\s*([^=:\s]+)\s*[=:]?\s*(.*)$", line)
        if match:
            values[match.group(1)] = _unescape(match.group(2).rstrip())
    return values


def write_properties(text: str, changes: dict[str, str]) -> str:
    """Replace the lines of the changed keys in place; comments, order and unknown keys stay as they are."""
    pending = dict(changes)
    lines = text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped[0] in "#!":
            continue
        match = re.match(r"^\s*([^=:\s]+)", line)
        if match and match.group(1) in pending:
            lines[index] = f"{match.group(1)}={_escape(pending.pop(match.group(1)))}"
    for key, value in pending.items():
        lines.append(f"{key}={_escape(value)}")
    return "\n".join(lines) + "\n"


_SECTION = re.compile(r"^\s*\[(.+)\]\s*$")


def read_ini(text: str) -> dict[str, str]:
    """Unreal .ini: "<section>/<key>" -> value. Repeated keys (arrays in Game.ini) keep the last value."""
    values: dict[str, str] = {}
    section = ""
    for line in text.splitlines():
        match = _SECTION.match(line)
        if match:
            section = match.group(1)
            continue
        if not line.strip() or line.lstrip()[0] in ";#" or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[f"{section}/{key.strip()}"] = value.strip()
    return values


def write_ini(text: str, changes: dict[str, str]) -> str:
    """Replace the changed keys in their sections; new keys go to the end of their section, new sections last."""
    lines = text.splitlines()
    pending = {k.rsplit("/", 1)[0]: {} for k in changes}
    for key, value in changes.items():
        section, name = key.rsplit("/", 1)
        pending[section][name] = value
    section, ends = "", {}
    for index, line in enumerate(lines):
        match = _SECTION.match(line)
        if match:
            section = match.group(1)
            continue
        if line.strip():
            ends[section] = index
        name = line.partition("=")[0].strip()
        if "=" in line and section in pending and name in pending[section]:
            lines[index] = f"{name}={pending[section].pop(name)}"
    for section_name, rest in sorted(((s, r) for s, r in pending.items() if r and s in ends),
                                     key=lambda item: ends[item[0]], reverse=True):
        at = ends[section_name] + 1
        lines[at:at] = [f"{k}={v}" for k, v in rest.items()]
        rest.clear()
    for section_name, rest in pending.items():
        if rest:
            lines += ["", f"[{section_name}]"] + [f"{k}={v}" for k, v in rest.items()]
    return "\n".join(lines) + "\n"


def _float_text(value: float) -> str:
    text = f"{value:.6f}".rstrip("0")
    return text + "0" if text.endswith(".") else text


def _get_path(data: dict[str, Any], key: str) -> Any:
    node: Any = data
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _set_path(data: dict[str, Any], key: str, value: Any) -> None:
    parts = key.split(".")
    node = data
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _coerce(spec: SettingSpec, value: SettingScalar) -> SettingScalar:
    """Validate a submitted value against its spec; raises ConfigError."""
    if spec.type == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower() == "true"
        raise ConfigError(f"{spec.label} must be true or false.")
    if spec.type == "int":
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ConfigError(f"{spec.label} must be a whole number.")
    if spec.type == "float":
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ConfigError(f"{spec.label} must be a number.")
    text = "" if value is None else str(value)
    if spec.type == "enum" and text not in spec.options:
        raise ConfigError(f"{spec.label} must be one of {', '.join(spec.options)}.")
    if "\n" in text and spec.type != "str":
        raise ConfigError(f"{spec.label} must be a single line.")
    return text


def _from_text(spec: SettingSpec, raw: Optional[str]) -> SettingScalar:
    if raw is None:
        return None
    if spec.type == "bool":
        return raw.strip().lower() == "true"
    if spec.type in ("int", "float"):
        try:
            number = float(raw.strip())
        except ValueError:
            return None
        return int(number) if spec.type == "int" and number.is_integer() else number
    return raw


def _from_json(spec: SettingSpec, raw: Any) -> SettingScalar:
    if raw is None:
        return None
    if isinstance(raw, list):
        return ", ".join(str(v) for v in raw)
    if spec.type == "enum" and isinstance(raw, bool):
        return "true" if raw else "false"
    if spec.type in ("str", "enum"):
        return str(raw)
    if spec.type == "bool":
        return bool(raw)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


# ---- service -----------------------------------------------------------------------------------------------

_STAT = 'stat -c "%u:%g %a" "$F" 2>/dev/null || stat -c "%u:%g %a" "$(dirname "$F")"'
_MOVE = 'mv -f "$F.gamefleet-tmp" "$F"'
_EXISTS = 'for f in $F; do [ -f "$f" ] && echo "$f"; done; exit 0'


@dataclass
class Target:
    server: GameServer
    layout: ConfigLayout
    fill: dict[str, str]

    def path(self, template: str) -> str:
        return template.format(**self.fill)

    @property
    def settings_file(self) -> Optional[str]:
        return self.path(self.layout.settings_file) if self.layout.settings_file else None

    @property
    def allowed(self) -> dict[str, str]:
        """Path -> label of every file this server may expose."""
        return {self.path(t): label for t, label in self.layout.files}


class ConfigService:
    def target(self, server: GameServer) -> Target:
        layout = LAYOUTS.get(GameServerType(server.game))
        if layout is None:
            raise ConfigError("Settings are not supported for this game yet.")
        if not server.data_path:
            raise ConfigError("GameFleet does not know where this server keeps its data (unknown image).")
        return Target(server, layout, {"data": server.data_path.rstrip("/"), "world": (server.world_path or "").rstrip("/")})

    async def info(self, server: GameServer) -> ConfigInfo:
        try:
            target = self.target(server)
        except ConfigError as exc:
            return ConfigInfo(supported=False, reason=str(exc))
        return await self._info(target)

    async def _info(self, target: Target) -> ConfigInfo:
        name = target.server.container_name
        files = await self._existing_files(target)
        settings: list[SettingValue] = []
        if target.settings_file:
            text = await self._read_text(name, target.settings_file)
            if text is not None:
                settings = await self._settings(target, text)
        return ConfigInfo(supported=True, settings_file=target.settings_file, settings=settings, files=files,
                          edit_when_stopped=target.layout.edit_when_stopped or None)

    async def _existing_files(self, target: Target) -> list[ConfigFile]:
        allowed = target.allowed
        try:
            async with docker_service.container_shell(target.server.container_name) as run:
                output = await run(_EXISTS, F="\n".join(allowed))
        except (RuntimeError, docker.errors.DockerException) as exc:
            raise ConfigError(f"Could not list the config files: {exc}")
        files = []
        for path in output.splitlines():
            if path in allowed:
                stat = await docker_service.stat_file(target.server.container_name, path)
                files.append(ConfigFile(path=path, label=allowed[path], size=int((stat or {}).get("size") or 0)))
        return files

    async def _settings(self, target: Target, text: str) -> list[SettingValue]:
        layout = target.layout
        env = await docker_service.env(target.server.container_name)
        if layout.format in ("properties", "ini"):
            values = read_properties(text) if layout.format == "properties" else read_ini(text)
            current = {spec.key: _from_text(spec, values.get(spec.key)) for spec in layout.specs}
        else:
            try:
                data = json.loads(text)
            except ValueError:
                raise ConfigError("The settings file is not valid JSON; fix it in the raw editor.")
            current = {spec.key: _from_json(spec, _get_path(data, spec.key)) for spec in layout.specs}
        locked: Optional[str] = None
        if layout.world_keys and layout.world_name_key:
            world = current.get(layout.world_name_key) or ("world" if layout.world_name_key == "level-name" else "")
            folder = layout.world_dir.format(**target.fill, name=world)
            if world and await docker_service.stat_file(target.server.container_name, folder):
                locked = "The world already exists; this would start a new one."
        # itzg rewrites a property from its variable on every start, so only the variable counts.
        overrides = {key: var for key, var in layout.env_map.items() if env.get(var) not in (None, "")}
        return [
            SettingValue(**spec.model_dump(), value=current.get(spec.key), env_override=overrides.get(spec.key),
                         locked=locked if spec.key in layout.world_keys else None)
            for spec in layout.specs
        ]

    async def update_settings(self, server: GameServer, values: dict[str, SettingScalar]) -> ConfigInfo:
        target = self.target(server)
        if not target.settings_file or not target.layout.specs:
            raise ConfigError("This game has no settings form; use the raw editor.")
        specs = {spec.key: spec for spec in target.layout.specs}
        unknown = set(values) - set(specs)
        if unknown:
            raise ConfigError(f"Unknown setting: {', '.join(sorted(unknown))}.")
        name = server.container_name
        text = await self._read_text(name, target.settings_file)
        if text is None:
            raise ConfigError("The settings file does not exist yet; start the server once.")
        current = {s.key: s for s in await self._settings(target, text)}
        coerced = {key: _coerce(specs[key], value) for key, value in values.items()}
        for key in coerced:
            if current[key].locked and coerced[key] != current[key].value:
                raise ConfigError(f"{specs[key].label} cannot change: {current[key].locked}")
            if current[key].env_override is not None and coerced[key] != current[key].value:
                # The image writes it from the container environment on every start: the change would be lost.
                raise ConfigError(f"{specs[key].label} is set by the container environment; change it there.")
        await self._check_stopped(target)
        if target.layout.format == "properties":
            changes = {key: ("true" if v is True else "false" if v is False else str(v)) for key, v in coerced.items()}
            new_text = write_properties(text, changes)
        elif target.layout.format == "ini":
            changes = {key: ("True" if v is True else "False" if v is False
                             else _float_text(v) if isinstance(v, float) else str(v)) for key, v in coerced.items()}
            if any("\n" in v for v in changes.values()):
                raise ConfigError("Values in an .ini file must be a single line.")
            new_text = write_ini(text, changes)
        else:
            data = json.loads(text)
            for key, value in coerced.items():
                spec = specs[key]
                if key == "tags":
                    value = [t.strip() for t in str(value).split(",") if t.strip()]
                elif spec.type == "enum" and value in ("true", "false"):
                    value = value == "true"
                _set_path(data, key, value)
            new_text = json.dumps(data, indent=2) + "\n"
        await self._write_text(name, target.settings_file, new_text)
        info = await self._info(target)
        info.restart_needed = True
        return info

    async def read(self, server: GameServer, path: str) -> FileContent:
        target = self.target(server)
        if path not in target.allowed:
            raise ConfigError("Not an editable file of this server.")
        stat = await docker_service.stat_file(server.container_name, path)
        if stat is None:
            raise ConfigError("The file does not exist.")
        size = int(stat.get("size") or 0)
        if size > MAX_FILE:
            raise ConfigError("The file is larger than 1 MiB; edit it on the host instead.")
        text = await self._read_text(server.container_name, path)
        if text is None:
            raise ConfigError("The file does not exist.")
        return FileContent(path=path, content=text, size=size)

    async def write(self, server: GameServer, path: str, content: str) -> FileWritten:
        target = self.target(server)
        if path not in target.allowed:
            raise ConfigError("Not an editable file of this server.")
        if len(content.encode()) > MAX_FILE:
            raise ConfigError("The content is larger than 1 MiB.")
        await self._check_stopped(target)
        if path.endswith(".json"):
            try:
                json.loads(content)
            except ValueError as exc:
                raise ConfigError(f"Not valid JSON: {exc}")
        await self._write_text(server.container_name, path, content)
        return FileWritten(path=path, size=len(content.encode()))

    async def _check_stopped(self, target: Target) -> None:
        if not target.layout.edit_when_stopped:
            return
        attrs = await docker_service.inspect(target.server.container_name)
        if (attrs.get("State") or {}).get("Running"):
            raise ConfigError(target.layout.edit_when_stopped)

    # ---- reading and writing through the archive endpoint ----

    async def _read_text(self, name: str, path: str) -> Optional[str]:
        try:
            data = await docker_service.read_file(name, path, limit=MAX_FILE + 1)
        except docker.errors.DockerException as exc:
            raise ConfigError(f"Could not read {path}: {getattr(exc, 'explanation', None) or exc}")
        return data

    async def _write_text(self, name: str, path: str, content: str) -> None:
        """Land the file next to its target with the target's owner and mode, then move it into place."""
        try:
            async with docker_service.container_shell(name) as run:
                owner, _, mode = (await run(_STAT, F=path)).strip().partition(" ")
                uid, _, gid = owner.partition(":")
                mode_bits = int(mode or "644", 8) if (mode or "").isdigit() else 0o644
                buf = io.BytesIO()
                payload = content.encode()
                with tarfile.open(fileobj=buf, mode="w") as tar:
                    info = tarfile.TarInfo(posixpath.basename(path) + ".gamefleet-tmp")
                    info.size, info.mtime, info.mode = len(payload), int(time.time()), mode_bits
                    info.uid, info.gid = int(uid or 0), int(gid or 0)
                    tar.addfile(info, io.BytesIO(payload))
                await docker_service.put_archive(name, posixpath.dirname(path), buf.getvalue())
                await run(_MOVE, F=path)
        except RuntimeError as exc:
            raise ConfigError(f"Could not write {path}: {exc}")
        except docker.errors.NotFound:
            raise ConfigError("The container or the file's folder does not exist.")
        except docker.errors.DockerException as exc:
            raise ConfigError(f"Could not write {path}: {getattr(exc, 'explanation', None) or exc}")


config_service = ConfigService()
