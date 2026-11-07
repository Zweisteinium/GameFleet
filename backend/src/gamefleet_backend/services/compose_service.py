"""Settings in a server's compose file: the `environment:` of its service, edited in place.

Images such as itzg/minecraft-server write their settings files from the container environment on every start,
so for a compose-run server the compose file is where a setting really lives. GameFleet finds the file through
the labels Docker Compose puts on the container, reads it through the servers folder (mounted at the same path,
see settings_service) and changes single lines, never re-serialising the document: hand-written files keep
their comments, order and quoting. Every write is checked twice before it replaces the file: the patched text
must parse to exactly the old document with only the intended variables changed, and `docker compose config`
must accept it. The previous file is kept as `<file>.gamefleet-bak`. A change applies when the container is
recreated (`docker compose up -d <service>`); until then the variable is reported as pending.

A variable written as `NAME=${OTHER}` takes its value from the project's .env file. When .env holds OTHER on
a single line, the form edits that line instead, checked the same way: `docker compose config` with the new
file must give the old configuration with only the intended variables changed.
"""
import asyncio
import json
import logging
import os
import re
import shutil
from dataclasses import dataclass
from typing import Any, Optional

import yaml
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from gamefleet_backend.db.models.game_server import GameServer
from gamefleet_backend.models.compose_info import ComposeFile, ComposeInfo, ComposeSetting
from gamefleet_backend.models.config_info import SettingScalar, SettingSpec
from gamefleet_backend.models.game_server_type import GameServerType
from gamefleet_backend.services.config_service import LAYOUTS, ConfigError, config_service
from gamefleet_backend.services.docker_service import docker_service
from gamefleet_backend.services.template_service import templates

log = logging.getLogger(__name__)

ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
INTERPOLATION = re.compile(r"(?<!\$)\$(\{|[A-Za-z_])")  # $VAR or ${VAR}, not the escaped $$
REFERENCE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$|^\$([A-Za-z_][A-Za-z0-9_]*)$")  # exactly one variable
DOTENV_LINE = re.compile(r"^(\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*)")
DOTENV_PLAIN = re.compile(r"[A-Za-z0-9_./:,@+%=-]*")  # written without quotes
MAX_DOTENV = 64 * 1024
MAX_COMPOSE = 256 * 1024
# Variables the settings form never offers: changing them turns the server into another one.
NOT_SETTINGS = {"EULA", "TYPE", "UID", "GID", "PUID", "PGID", "TZ"}
# Minecraft properties whose variables are edited as text areas with a rendered preview.
MOTD_VARS = {"MOTD"}


class ComposeError(ConfigError):
    """A problem with the compose file the user can act on; shown as is."""


@dataclass
class Project:
    name: str
    service: str
    working_dir: str
    files: list[str]

    @property
    def file(self) -> str:
        return self.files[0]

    @property
    def dotenv(self) -> str:
        return os.path.join(self.working_dir, ".env")

    def args(self, files: Optional[list[str]] = None, env_file: Optional[str] = None) -> list[str]:
        result = ["-p", self.name, "--project-directory", self.working_dir]
        for f in files or self.files:
            result += ["-f", f]
        if env_file:
            result += ["--env-file", env_file]
        return result


async def compose_cli(project: Project, *args: str, files: Optional[list[str]] = None,
                      env_file: Optional[str] = None) -> str:
    process = await asyncio.create_subprocess_exec(
        "docker", "compose", *project.args(files, env_file), *args, cwd=project.working_dir,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, err = await process.communicate()
    if process.returncode:
        message = (err or out).decode("utf-8", "replace").strip().splitlines()
        raise ComposeError(f"docker compose {args[0]} failed: {message[-1] if message else process.returncode}")
    return out.decode("utf-8", "replace")


# ---- specs: which variables the form shows ----------------------------------------------------------------

def _template_spec(variable) -> Optional[SettingSpec]:
    kind = {"text": "str", "number": "int", "select": "enum", "boolean": "bool", "memory": "str"}.get(variable.type)
    if kind is None or not variable.settings:
        return None  # secrets and modpack pickers stay in the file
    return SettingSpec(key=variable.env, label=variable.label, type=kind, description=variable.help or "",
                       options=[o.value for o in variable.options], group=variable.group or "General")


def _e(env: str, label: str, type: str, description: str = "", options: tuple[str, ...] = (), group: str = "") -> SettingSpec:
    return SettingSpec(key=env, label=label, type=type, description=description, options=list(options), group=group)


# Images GameFleet has no template for, by the last two parts of the repository.
IMAGE_SPECS: dict[str, tuple[SettingSpec, ...]] = {
    "hermsi/ark-server": (
        _e("SERVER_MAP", "Map", "enum", "Each map keeps its own save.",
           ("TheIsland", "TheCenter", "ScorchedEarth_P", "Ragnarok", "Aberration_P", "Extinction", "Valguero_P",
            "Genesis", "CrystalIsles", "Gen2", "LostIsland", "Fjordur"), "General"),
        _e("SERVER_PASSWORD", "Join password", "secret", "Empty lets anyone join.", group="Access"),
        _e("ADMIN_PASSWORD", "Admin password", "secret", "For enablecheats and RCON.", group="Access"),
        _e("GAME_MOD_IDS", "Mods", "str", "Steam Workshop IDs, comma separated; installed on start.", group="Software"),
        _e("UPDATE_ON_START", "Update on start", "bool", group="Updates and backups"),
        _e("PRE_UPDATE_BACKUP", "Back up before updates", "bool", group="Updates and backups"),
        _e("BACKUP_ON_STOP", "Back up on stop", "bool", group="Updates and backups"),
        _e("WARN_ON_STOP", "Warn players before stopping", "bool", "Announces the shutdown in chat first.",
           group="Updates and backups"),
    ),
}


@dataclass
class Offered:
    env: str
    spec: SettingSpec
    file_key: Optional[str] = None  # the settings-file key the variable writes, if any
    show_if: Optional[dict[str, list[str]]] = None  # template condition on other variables
    defaults: Optional[dict[str, str]] = None  # template defaults, to evaluate show_if for unset variables


def specs_for(server: GameServer, image: str) -> list[Offered]:
    """The variables the form offers for the server: the layout's mirrored properties first, then the
    variables of the template for its image."""
    result: list[Offered] = []
    seen: set[str] = set()
    layout = LAYOUTS.get(server.game)
    if layout:
        for spec in layout.specs:
            env = layout.env_map.get(spec.key)
            if env and env not in seen:
                result.append(Offered(env, spec, spec.key))
                seen.add(env)
    name = image.split("@")[0]
    repository = name.rsplit(":", 1)[0] if ":" in name.rsplit("/", 1)[-1] else name
    short = "/".join(repository.split("/")[-2:])  # ghcr.io/lloesche/valheim-server is lloesche/valheim-server
    for spec in IMAGE_SPECS.get(short, ()):
        if spec.key not in seen:
            result.append(Offered(spec.key, spec))
            seen.add(spec.key)
    for template in templates().values():
        if "/".join(template.image.split("/")[-2:]) != short:
            continue
        defaults = {v.env: v.default or "" for v in template.variables}
        for variable in template.variables:
            if variable.env in seen or variable.env in NOT_SETTINGS:
                continue
            spec = _template_spec(variable)
            if spec:
                result.append(Offered(variable.env, spec, None, variable.show_if or None, defaults))
                seen.add(variable.env)
    return result


def applies(offered: Offered, resolved: dict[str, Optional[str]]) -> bool:
    if not offered.show_if:
        return True
    current = {**(offered.defaults or {}), **{k: v for k, v in resolved.items() if v is not None}}
    return all(current.get(env) in allowed for env, allowed in offered.show_if.items())


# ---- reading the file -------------------------------------------------------------------------------------

def project_of(attrs: dict[str, Any]) -> Optional[Project]:
    labels = (attrs.get("Config") or {}).get("Labels") or {}
    name, service = labels.get("com.docker.compose.project"), labels.get("com.docker.compose.service")
    working_dir = labels.get("com.docker.compose.project.working_dir")
    files = [f for f in (labels.get("com.docker.compose.project.config_files") or "").split(",") if f]
    if not (name and service and working_dir and files):
        return None
    return Project(name, service, working_dir, files)


def _load(text: str) -> Any:
    loader = YAML(typ="rt")
    return loader.load(text)


def service_environment(document: Any, service: str) -> tuple[Any, Any]:
    """(service mapping, its environment node or None)."""
    services = document.get("services") if isinstance(document, CommentedMap) else None
    node = services.get(service) if isinstance(services, CommentedMap) else None
    if not isinstance(node, CommentedMap):
        raise ComposeError(f"The compose file has no service {service}.")
    env = node.get("environment")
    if env is not None and not isinstance(env, (CommentedMap, CommentedSeq)):
        raise ComposeError("The environment of the service is neither a mapping nor a list.")
    return node, env


def raw_environment(env: Any) -> dict[str, Optional[str]]:
    """Variables as written in the file (before interpolation); None for a bare `- NAME` pass-through."""
    if env is None:
        return {}
    if isinstance(env, CommentedMap):
        return {str(k): None if v is None else str(v) if not isinstance(v, bool) else str(v).lower() for k, v in env.items()}
    result: dict[str, Optional[str]] = {}
    for item in env:
        key, sep, value = str(item).partition("=")
        result[key] = value if sep else None
    return result


def _scalar_end(line: str, start: int) -> Optional[int]:
    """End of the single-line scalar starting at `start`, or None when it continues on the next line."""
    if start >= len(line):
        return None
    quote = line[start]
    if quote in "\"'":
        i = start + 1
        while i < len(line):
            if quote == '"' and line[i] == "\\":
                i += 2
                continue
            if line[i] == quote:
                if quote == "'" and line[i + 1:i + 2] == "'":
                    i += 2
                    continue
                return i + 1
            i += 1
        return None  # the quoted string goes on
    if quote in "|>":
        return None  # block scalar
    comment = re.search(r"\s#", line[start:])
    value = line[start:start + comment.start()] if comment else line[start:]
    return start + len(value.rstrip())  # the spaces before a comment stay, so aligned comments stay aligned


def _quote(value: str) -> str:
    """A YAML double-quoted scalar (JSON is valid YAML) with $ escaped for compose."""
    return json.dumps(value.replace("$", "$$"), ensure_ascii=False)


@dataclass
class Located:
    line: int  # 0-based line of the key (map) or item (list)
    start: int  # column where the value (map) or the item scalar (list) starts
    end: int


def locate(lines: list[str], env: Any) -> dict[str, Optional[Located]]:
    """Where each variable's value sits, None for values that span lines (not editable here)."""
    found: dict[str, Optional[Located]] = {}
    if isinstance(env, CommentedMap):
        for key in env:
            key_line, _ = env.lc.key(key)
            value_line, value_col = env.lc.value(key)
            if env[key] is None or value_line != key_line:
                found[str(key)] = None
                continue
            end = _scalar_end(lines[value_line], value_col)
            found[str(key)] = Located(value_line, value_col, end) if end else None
    elif isinstance(env, CommentedSeq):
        for index, item in enumerate(env):
            line, col = env.lc.item(index)
            end = _scalar_end(lines[line], col)
            found[str(item).partition("=")[0]] = Located(line, col, end) if end else None
    return found


def patch(text: str, service: str, changes: dict[str, Optional[str]]) -> str:
    """The compose text with the variables changed (None removes one), touching only their lines."""
    document = _load(text)
    node, env = service_environment(document, service)
    lines = text.split("\n")
    places = locate(lines, env)
    is_list = isinstance(env, CommentedSeq)
    removals: list[int] = []
    additions: list[str] = []
    for key, value in changes.items():
        if not ENV_NAME.match(key):
            raise ComposeError(f"{key} is not a variable name.")
        if value is not None and ("\x00" in value or "\r" in value):
            raise ComposeError(f"{key} contains a character the file cannot hold.")
        if key in places:
            place = places[key]
            if place is None:
                raise ComposeError(f"{key} spans several lines in the compose file; change it there.")
            if value is None:
                removals.append(place.line)
                continue
            line = lines[place.line]
            rendered = _quote(f"{key}={value}") if is_list else _quote(value)
            lines[place.line] = line[:place.start] + rendered + line[place.end:]
        elif value is not None:
            additions.append(_quote(f"{key}={value}") if is_list else f"{key}: {_quote(value)}")
    if additions:
        if env is not None and len(env):
            if not all(places.values()):
                raise ComposeError("Some variables span several lines; add new ones in the file.")
            last_line = max(p.line for p in places.values() if p)
            if is_list:  # the item position points at the scalar; the dash sits two columns left
                prefix = " " * max(env.lc.item(0)[1] - 2, 0) + "- "
            else:
                prefix = " " * env.lc.key(next(iter(env)))[1]
            insert_at = last_line + 1
        elif env is not None:  # `environment: {}` or `[]`: not worth guessing a layout
            raise ComposeError("The service has an empty environment block; add the variables in the file.")
        else:
            anchor = next((k for k in node if not isinstance(node[k], (CommentedMap, CommentedSeq))
                           and node.lc.key(k)[0] == node.lc.value(k)[0]
                           and _scalar_end(lines[node.lc.value(k)[0]], node.lc.value(k)[1])), None)
            if anchor is None:
                raise ComposeError("Cannot find where to add an environment block; add it in the file.")
            line, col = node.lc.key(anchor)
            lines.insert(line + 1, " " * col + "environment:")
            insert_at, prefix = line + 2, " " * (col + 2)
        for offset, addition in enumerate(additions):
            lines.insert(insert_at + offset, prefix + addition)
    for line_no in sorted(removals, reverse=True):
        del lines[line_no]
    return "\n".join(lines)


def check_patch(old: str, new: str, service: str, changes: dict[str, Optional[str]]) -> None:
    """The patched file must be the old document with exactly these variables changed."""
    try:
        before, after = yaml.safe_load(old), yaml.safe_load(new)
    except yaml.YAMLError as exc:
        raise ComposeError(f"The change would break the YAML: {exc}")

    def env_of(doc: Any) -> dict[str, Optional[str]]:
        env = (((doc or {}).get("services") or {}).get(service) or {}).get("environment")
        if isinstance(env, list):
            return {str(i).partition("=")[0]: str(i).partition("=")[2] if "=" in str(i) else None for i in env}
        return {str(k): None if v is None else str(v).lower() if isinstance(v, bool) else str(v) for k, v in (env or {}).items()}

    expected = env_of(before)
    for key, value in changes.items():
        if value is None:
            expected.pop(key, None)
        else:
            expected[key] = value.replace("$", "$$")
    if env_of(after) != expected:
        raise ComposeError("The change did not come out as intended; nothing was written. Edit the file by hand.")
    for doc in (before, after):
        doc["services"][service].pop("environment", None)
    if before != after:
        raise ComposeError("The change would touch more than the environment; nothing was written.")


def dotenv_locate(text: str) -> dict[str, Optional[Located]]:
    """Where each variable's value sits in a .env file; None when it spans lines or is defined twice."""
    found: dict[str, Optional[Located]] = {}
    for index, line in enumerate(text.split("\n")):
        match = DOTENV_LINE.match(line)
        if not match:
            continue
        name, start = match.group(2), match.end()
        if name in found:
            found[name] = None
            continue
        rest = line[start:]
        if rest[:1] in ("'", '"'):
            i = 1
            while i < len(rest) and rest[i] != rest[0]:
                i += 2 if rest[0] == '"' and rest[i] == "\\" else 1
            found[name] = Located(index, start, start + i + 1) if i < len(rest) else None
        else:
            comment = re.search(r"\s#", rest)
            value = rest[:comment.start()] if comment else rest
            found[name] = Located(index, start, start + len(value.rstrip()))
    return found


def dotenv_quote(name: str, value: str) -> str:
    if any(ch in value for ch in "\n\r\x00"):
        raise ComposeError(f"{name} must be a single line.")
    if DOTENV_PLAIN.fullmatch(value):
        return value
    if "'" not in value:
        return f"'{value}'"  # taken literally: no escapes, no interpolation
    raise ComposeError(f"{name} contains a ' and other special characters; change it in .env by hand.")


def dotenv_patch(text: str, changes: dict[str, str]) -> str:
    lines = text.split("\n")
    places = dotenv_locate(text)
    for name, value in changes.items():
        place = places.get(name)
        if place is None:
            raise ComposeError(f"{name} is not on a single line of .env; change it there.")
        line = lines[place.line]
        lines[place.line] = line[:place.start] + dotenv_quote(name, value) + line[place.end:]
    return "\n".join(lines)


def _write_like(path: str, content: str, like: os.stat_result) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, like.st_mode & 0o777)
    with os.fdopen(fd, "w") as file:
        file.write(content)
    if os.geteuid() == 0:
        os.chown(path, like.st_uid, like.st_gid)


class ComposeService:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    async def project(self, server: GameServer) -> tuple[Project, dict[str, Any]]:
        attrs = await docker_service.inspect(server.container_name)
        project = project_of(attrs)
        if project is None:
            raise ComposeError("This container was not started by Docker Compose, so it has no compose file to edit.")
        if len(project.files) != 1:
            raise ComposeError("This project combines several compose files; edit them by hand.")
        if not os.path.isfile(project.file):
            raise ComposeError(f"{project.file} is not visible to GameFleet. Mount its folder into the backend "
                               "at the same path (see GAMEFLEET_SERVERS_DIR).")
        return project, attrs

    def _read(self, project: Project) -> str:
        if os.path.getsize(project.file) > MAX_COMPOSE:
            raise ComposeError("The compose file is too large to edit here.")
        with open(project.file, encoding="utf-8") as file:
            return file.read()

    async def resolved(self, project: Project, files: Optional[list[str]] = None) -> dict[str, Optional[str]]:
        """The service environment after interpolation and env_file, as compose hands it to Docker."""
        config = json.loads(await compose_cli(project, "config", "--format", "json", files=files))
        env = ((config.get("services") or {}).get(project.service) or {}).get("environment") or {}
        # `config` prints a valid compose file, so a literal $ comes back escaped as $$.
        return {k: None if v is None else str(v).replace("$$", "$") for k, v in env.items()}

    async def pending(self, project: Project, attrs: dict[str, Any], resolved: dict[str, Optional[str]]) -> list[str]:
        container = dict(e.partition("=")[::2] for e in (attrs.get("Config") or {}).get("Env") or [])
        image_env: dict[str, str] = {}
        try:
            image = await docker_service.inspect_image(attrs.get("Image", ""))
            image_env = dict(e.partition("=")[::2] for e in (image.get("Config") or {}).get("Env") or [])
        except Exception:  # image gone: compare what we can
            pass
        changed = [k for k, v in resolved.items() if v is not None and container.get(k) != v]
        # Set in the container by an earlier version of the file, removed since.
        changed += [k for k, v in container.items() if k not in resolved and image_env.get(k) != v]
        return sorted(set(changed))

    async def info(self, server: GameServer) -> ComposeInfo:
        try:
            project, attrs = await self.project(server)
        except ComposeError as exc:
            return ComposeInfo(supported=False, reason=str(exc))
        text = await asyncio.to_thread(self._read, project)
        _, env = service_environment(_load(text), project.service)
        raw = raw_environment(env)
        places = locate(text.split("\n"), env)
        resolved = await self.resolved(project)
        dotenv = await asyncio.to_thread(self._read_dotenv, project)
        dotenv_places = dotenv_locate(dotenv) if dotenv is not None else {}
        # Current values of the settings file, and which keys are fixed because the world exists.
        file_values: dict[str, SettingScalar] = {}
        locked: dict[str, str] = {}
        try:
            for s in (await config_service.info(server)).settings:
                file_values[s.key] = s.value
                if s.locked:
                    locked[s.key] = s.locked
        except Exception as exc:  # the file view is a bonus here
            log.debug("No settings file for %s: %s", server.container_name, exc)
        settings = []
        for offered in specs_for(server, (attrs.get("Config") or {}).get("Image", "")):
            if not applies(offered, resolved):
                continue
            env_name, spec, file_key = offered.env, offered.spec, offered.file_key
            value = resolved.get(env_name)
            readonly = None
            env_file = None
            reference = REFERENCE.match(raw.get(env_name) or "")
            if reference and dotenv_places.get(reference.group(1) or reference.group(2)):
                env_file = project.dotenv
            elif env_name in raw and raw[env_name] is not None and INTERPOLATION.search(raw[env_name]):
                readonly = f"Set from a variable ({raw[env_name]}) that is not on a single line of .env; change it there."
            elif env_name in resolved and env_name not in raw:
                readonly = "Set in an env_file; change it there."
            elif env_name in places and places[env_name] is None:
                readonly = "Spans several lines in the compose file; change it there."
            elif file_key and file_key in locked:
                readonly = locked[file_key]
            fields = spec.model_dump()
            if spec.type == "enum" and value and value not in spec.options:
                fields["options"] = [*spec.options, value]  # a modded map or a value the list does not know
            settings.append(ComposeSetting(
                **fields, env=env_name, value=None if spec.type == "secret" else _typed(spec, value),
                readonly=readonly, env_file=env_file, is_set=bool(value),
                file_value=file_values.get(file_key) if file_key else None,
                multiline=env_name in MOTD_VARS, motd=env_name in MOTD_VARS and server.game == GameServerType.minecraft,
            ))
        return ComposeInfo(supported=True, file=project.file, project=project.name, service=project.service,
                           settings=settings, pending=await self.pending(project, attrs, resolved))

    def _lock(self, server: GameServer) -> asyncio.Lock:
        return self._locks.setdefault(server.id, asyncio.Lock())

    async def update(self, server: GameServer, values: dict[str, SettingScalar]) -> ComposeInfo:
        async with self._lock(server):
            project, attrs = await self.project(server)
            current = {s.env: s for s in (await self.info(server)).settings}
            unknown = set(values) - set(current)
            if unknown:
                raise ComposeError(f"Not a setting of this server: {', '.join(sorted(unknown))}.")
            changes: dict[str, Optional[str]] = {}
            dotenv_changes: dict[str, str] = {}  # .env variable -> value
            via_dotenv: dict[str, str] = {}  # service variable -> value, as it should come out
            text = await asyncio.to_thread(self._read, project)
            raw = raw_environment(service_environment(_load(text), project.service)[1])
            for env, value in values.items():
                setting = current[env]
                if setting.readonly:
                    raise ComposeError(f"{setting.label}: {setting.readonly}")
                if setting.env_file:
                    if value is None:
                        raise ComposeError(f"{setting.label} comes from .env; remove it there.")
                    reference = REFERENCE.match(raw[env] or "")
                    assert reference
                    dotenv_changes[reference.group(1) or reference.group(2)] = via_dotenv[env] = _text(setting, value)
                else:
                    changes[env] = None if value is None else _text(setting, value)
            if dotenv_changes:
                await self._replace_dotenv(project, dotenv_changes, via_dotenv)
            if changes:
                await self._replace(project, lambda text: patch(text, project.service, changes),
                                    lambda old, new: check_patch(old, new, project.service, changes))
        return await self.info(server)

    def _read_dotenv(self, project: Project) -> Optional[str]:
        try:
            if os.path.getsize(project.dotenv) > MAX_DOTENV:
                return None
            with open(project.dotenv, encoding="utf-8") as file:
                return file.read()
        except (OSError, UnicodeDecodeError):
            return None

    async def _replace_dotenv(self, project: Project, changes: dict[str, str], expected: dict[str, str]) -> None:
        """Patch .env; `docker compose config` with the new file must differ only in the expected variables."""
        own = [name for name in changes if name.startswith(("COMPOSE_", "DOCKER_"))]
        if own:  # compose reads these itself (project name, ...): `config` with -p would not show the change
            raise ComposeError(f"{', '.join(own)} configures Docker Compose itself; change it in .env by hand.")
        old = await asyncio.to_thread(self._read_dotenv, project)
        if old is None:
            raise ComposeError(f"{project.dotenv} cannot be read.")
        new = dotenv_patch(old, changes)
        if new == old:
            return
        folder = os.path.dirname(project.dotenv)
        temp = os.path.join(folder, ".env.gamefleet-tmp")
        like = os.stat(project.dotenv)
        await asyncio.to_thread(_write_like, temp, new, like)
        try:
            before = json.loads(await compose_cli(project, "config", "--format", "json"))
            after = json.loads(await compose_cli(project, "config", "--format", "json", env_file=temp))
            env_before = before["services"][project.service].pop("environment", None) or {}
            env_after = after["services"][project.service].pop("environment", None) or {}
            want = {**env_before, **{k: v.replace("$", "$$") for k, v in expected.items()}}
            if env_after != want:
                raise ComposeError("The change did not come out as intended; nothing was written. Edit .env by hand.")
            if before != after:
                raise ComposeError("The variable is also used elsewhere in the compose file; change it in .env by hand.")
            backup = project.dotenv + ".gamefleet-bak"
            await asyncio.to_thread(shutil.copy2, project.dotenv, backup)
            if os.geteuid() == 0:
                os.chown(backup, like.st_uid, like.st_gid)
            os.replace(temp, project.dotenv)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        log.info("Updated %s (backup in %s.gamefleet-bak)", project.dotenv, project.dotenv)

    async def read_file(self, server: GameServer) -> ComposeFile:
        project, _ = await self.project(server)
        return ComposeFile(path=project.file, content=await asyncio.to_thread(self._read, project))

    async def write_file(self, server: GameServer, content: str) -> ComposeFile:
        if len(content.encode()) > MAX_COMPOSE:
            raise ComposeError("The file is too large.")
        async with self._lock(server):
            project, _ = await self.project(server)

            def check(_old: str, new: str) -> None:
                try:
                    yaml.safe_load(new)
                except yaml.YAMLError as exc:
                    raise ComposeError(f"Not valid YAML: {exc}")
            await self._replace(project, lambda _text: content, check)
        return await self.read_file(server)

    async def _replace(self, project: Project, change, check) -> None:
        """Write the changed file next to the old one, let compose validate it, keep a backup, swap it in."""
        old = await asyncio.to_thread(self._read, project)
        new = change(old)
        if new == old:
            return
        check(old, new)
        folder, name = os.path.split(project.file)
        temp = os.path.join(folder, f".{name}.gamefleet-tmp")
        like = os.stat(project.file)
        await asyncio.to_thread(_write_like, temp, new, like)
        try:
            config = json.loads(await compose_cli(project, "config", "--format", "json", files=[temp]))
            if project.service not in (config.get("services") or {}):
                raise ComposeError(f"The file no longer defines the service {project.service}.")
            backup = project.file + ".gamefleet-bak"
            await asyncio.to_thread(shutil.copy2, project.file, backup)
            if os.geteuid() == 0:
                os.chown(backup, like.st_uid, like.st_gid)
            os.replace(temp, project.file)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        log.info("Updated %s (backup in %s.gamefleet-bak)", project.file, project.file)

    async def has_pending(self, server: GameServer) -> bool:
        try:
            project, attrs = await self.project(server)
            return bool(await self.pending(project, attrs, await self.resolved(project)))
        except Exception:
            return False

    async def recreate(self, server: GameServer) -> None:
        """`docker compose up -d` for the server's service: applies the file, starts the container."""
        async with self._lock(server):
            project, _ = await self.project(server)
            await compose_cli(project, "up", "--detach", "--no-deps", "--no-build", project.service)
        docker_service.forget(server.container_name)


def _typed(spec: SettingSpec, value: Optional[str]) -> SettingScalar:
    if value is None:
        return None
    if spec.type == "bool":
        return value.strip().lower() == "true"
    if spec.type in ("int", "float"):
        try:
            number = float(value)
        except ValueError:
            return value
        return int(number) if spec.type == "int" and number.is_integer() else number
    return value


def _text(spec: SettingSpec, value: SettingScalar) -> str:
    if spec.type == "bool":
        if isinstance(value, str):
            value = value.lower() == "true"
        return "true" if value else "false"
    if spec.type == "int":
        try:
            return str(int(value))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ComposeError(f"{spec.label} must be a whole number.")
    if spec.type == "float":
        try:
            return str(float(value))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ComposeError(f"{spec.label} must be a number.")
    text = str(value)
    if spec.type == "enum" and spec.options and text not in spec.options:
        raise ComposeError(f"{spec.label} must be one of {', '.join(spec.options)}.")
    return text


compose_service = ComposeService()
