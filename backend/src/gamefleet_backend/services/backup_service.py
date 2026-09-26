"""Restoring the world of a Docker-linked server from a backup.

GameFleet does not make backups; game servers and their mods already do (ServerUtilities and FTB Backups
write zips to `backups/`, the Valheim and Satisfactory images keep copies in `/config/backups`, Factorio keeps
autosaves, ARK timestamped .ark files). Each game's WorldLayout names where those live; any folder with
"backup" in its name just below the data directory is searched as well. A restore takes one of them, or an
uploaded file, and puts the world where the game loads it from. The game is stopped for that and started again
afterwards; a copy of the current world can be kept first (`<data_path>/gamefleet-backups`).

Every file operation runs inside a container that shares the game's mounts: the game container itself while
it runs, else a helper made from the same image (docker_service.create_helper). The backend never needs the
host paths, and stopped servers work the same as running ones. A backup is copied here (or uploaded), reduced
to the files that belong to the world, and streamed as a plain tar into a staging directory; a short sh script
then swaps it in and hands ownership to the game's user.
"""
import asyncio
import logging
import os
import posixpath
import re
import tarfile
import tempfile
import time
import zipfile
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncIterator, BinaryIO, Callable, Iterator, Literal, Optional

import docker.errors
from pydantic import BaseModel

from gamefleet_backend.db.models.game_server import GameServer
from gamefleet_backend.models.game_server_type import GameServerType
from gamefleet_backend.services.docker_service import docker_service

log = logging.getLogger(__name__)

COPY_DIR = "gamefleet-backups"  # under data_path: the copies kept before a restore
JUNK = re.compile(r"(^|/)(__MACOSX|\.DS_Store|Thumbs\.db|desktop\.ini|session\.lock)(/|$)")
STAGING = ".gamefleet-restore"  # inside the target's parent, on the same filesystem so the final move is a rename
CHUNK = 1 << 20
ARCHIVE = r"\.(zip|tar|tgz|tar\.(gz|xz|bz2|zst))$"


class BackupError(Exception):
    """A problem the user can act on (wrong archive, unknown layout, server busy); the message is shown as is."""


# ---- per-game layout ------------------------------------------------------------------------------------

@dataclass(frozen=True)
class WorldLayout:
    # Directory the restore fills: {data} and {world} are the server's data_path and world_path, {name} the
    # world name. "dir": the world is this folder, replaced as a whole. "files": save files placed into it.
    target: str
    kind: Literal["dir", "files"]
    accept: str  # file picker filter
    hint: str  # what to upload, shown in the dialog
    # Where the server's own backups are (same placeholders) and which file names count as one.
    sources: tuple[str, ...] = ()
    backup_files: str = ARCHIVE
    marker: str = ""  # dir: the file that marks a world root inside an archive
    requires: tuple[str, ...] = ()  # dir: paths under the root that must exist (tells the editions apart)
    forbids: tuple[str, ...] = ()
    exts: tuple[str, ...] = ()  # files: extensions taken from an archive
    self_marker: str = ""  # files: an archive containing this file *is* one save (Factorio saves are zips)
    complete: tuple[str, ...] = ()  # files: extensions that must all be present per save (Valheim .db + .fwl)
    strip: str = ""  # files: suffix of backup copies, removed to get the save's own name
    rename: bool = False  # files: one save takes the configured name
    nest: bool = False  # files: <target>/<stem>/<file> (ARK: SA keeps each map in its own folder)
    name_env: tuple[str, ...] = ()  # container variables that carry the world name, first set wins
    name_property: str = ""  # key in {data}/server.properties
    default_name: str = ""


ARCHIVES = ".zip,.tar,.tar.gz,.tgz,.tar.xz,.tar.zst"
ARK_COPY = r"_\d\d\.\d\d\.\d{4}_\d\d\.\d\d\.\d\d"  # TheIsland_27.09.2026_00.30.00.ark
LAYOUTS: dict[GameServerType, WorldLayout] = {
    GameServerType.minecraft: WorldLayout(
        "{data}/{name}", "dir", ARCHIVES,
        "An archive that contains a world folder (a level.dat inside), as written by backup mods or hosting "
        "panels. The folder replaces the current world; Paper's _nether and _the_end folders are restored with "
        "it when the archive has them.",
        # ServerUtilities, FTB Utilities and FTB Backups; Simple Backups; Textile Backup (backup/<world>/)
        sources=("{data}/backups", "{data}/simplebackups", "{data}/backup"),
        marker="level.dat", forbids=("db/CURRENT",),
        name_env=("LEVEL",), name_property="level-name", default_name="world",
    ),
    GameServerType.minecraft_bedrock: WorldLayout(
        "{data}/worlds/{name}", "dir", ".mcworld," + ARCHIVES,
        "A .mcworld file or an archive of the world folder (level.dat and db inside). It replaces the current world.",
        sources=("{data}/backups",), backup_files=r"(\.mcworld|" + ARCHIVE[1:-1] + r")$",
        marker="level.dat", requires=("db/CURRENT",),
        name_env=("LEVEL_NAME",), name_property="level-name", default_name="Bedrock level",
    ),
    GameServerType.factorio: WorldLayout(
        "{world}", "files", ARCHIVES,
        "A Factorio save (.zip). With SAVE_NAME set it takes that name, otherwise the server loads it as the "
        "newest save on start.",
        sources=("{world}",), backup_files=r"\.zip$|" + ARCHIVE,
        exts=(".zip",), self_marker="level-init.dat", rename=True, name_env=("SAVE_NAME",),
    ),
    GameServerType.satisfactory: WorldLayout(
        "{world}/server", "files", ".sav," + ARCHIVES,
        "A .sav file (or an archive of them) goes into the server's save folder. The server loads the newest save "
        "of its session on start; pick it in the Server Manager if it does not.",
        sources=("{data}/backups", "{world}/server"), backup_files=r"^(?!ServerSettings\.).*\.sav$|" + ARCHIVE,
        exts=(".sav",),
    ),
    GameServerType.valheim: WorldLayout(
        "{world}", "files", ARCHIVES,
        "An archive with the .db and .fwl pair of a world; both are renamed to the server's world name.",
        sources=("{data}/backups", "/home/steam/backups"),
        exts=(".db", ".fwl"), complete=(".db", ".fwl"), strip=r"_backup_auto-\d+$", rename=True,
        name_env=("WORLD_NAME", "WORLD"),
    ),
    GameServerType.ark_ase: WorldLayout(
        "{world}/SavedArks", "files", ".ark,.arkprofile,.arktribe," + ARCHIVES,
        "The map's .ark file, optionally with .arkprofile and .arktribe files, placed into SavedArks. Untested.",
        sources=("{world}/SavedArks", "{data}/backup", "{data}/backups"), backup_files=ARK_COPY + r"\.ark$|" + ARCHIVE,
        exts=(".ark", ".arkprofile", ".arktribe", ".arktributetribe"), strip=ARK_COPY + "$",
    ),
    GameServerType.ark_asa: WorldLayout(
        "{world}/SavedArks", "files", ".ark,.arkprofile,.arktribe," + ARCHIVES,
        "The map's .ark file, optionally with .arkprofile and .arktribe files, placed into SavedArks/<map>. Untested.",
        sources=("{world}/SavedArks", "{data}/backup", "{data}/backups"), backup_files=ARK_COPY + r"\.ark$|" + ARCHIVE,
        exts=(".ark", ".arkprofile", ".arktribe", ".arktributetribe"), strip=ARK_COPY + "$", nest=True,
    ),
}


class Backup(BaseModel):
    path: str  # inside the container; identifies the backup in restore and download calls
    file: str
    folder: str  # relative to the data directory, e.g. "backups"
    size: int
    created: float  # unix time (modification time)
    gamefleet: bool = False  # a copy GameFleet kept before a restore


class BackupJob(BaseModel):
    """A restore in progress or just finished (one per server, kept in memory)."""
    action: Literal["restore"] = "restore"
    source: str  # file name shown to the user
    phase: Literal["preparing", "stopping", "snapshot", "applying", "starting", "done", "failed"]
    started_at: float
    finished_at: Optional[float] = None
    error: Optional[str] = None
    warning: Optional[str] = None
    snapshot: Optional[str] = None  # the copy of the previous world, if one was kept
    restarted: bool = False


class BackupInfo(BaseModel):
    supported: bool
    reason: Optional[str] = None  # why not
    world: Optional[str] = None  # the world that a restore replaces, e.g. "World"
    target: Optional[str] = None  # path inside the container
    kind: Optional[Literal["dir", "files"]] = None
    accept: Optional[str] = None
    hint: Optional[str] = None
    running: bool = False
    locations: list[str] = []  # folders that were searched and exist
    backups: list[Backup] = []
    job: Optional[BackupJob] = None


@dataclass
class World:
    """Where a server keeps its world, resolved from the container."""
    server: GameServer
    layout: WorldLayout
    name: str  # configured world/save name ("" when the game has none)
    target: str  # absolute path inside the container
    copies: str  # where copies before a restore go
    sources: list[str]  # backup folders to search
    running: bool


@dataclass
class Entry:
    name: str  # normalised archive path, "/" separated
    size: int
    open: Callable[[], BinaryIO]


@dataclass
class Plan:
    """What an upload turns into: archive entries and their path below the staging directory."""
    files: list[tuple[Entry, str]]
    summary: str
    cleanup: Callable[[], None] = field(default=lambda: None)


# ---- reading archives ---------------------------------------------------------------------------------------

def _normalise(name: str) -> Optional[str]:
    parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts or ".." in parts or JUNK.search("/".join(parts)):
        return None
    return "/".join(parts)


def open_upload(path: str, filename: str) -> tuple[list[Entry], Callable[[], None], bool]:
    """Entries of a zip, a tar (any compression) or, failing both, the file itself. Returns the entries, how
    to close the container and whether it was an archive."""
    if zipfile.is_zipfile(path):
        zf = zipfile.ZipFile(path)
        entries = []
        for info in zf.infolist():
            if info.is_dir() or (name := _normalise(info.filename)) is None:
                continue
            entries.append(Entry(name, info.file_size, lambda i=info: zf.open(i)))
        return entries, zf.close, True
    try:
        tf = tarfile.open(path, "r:*")
    except tarfile.ReadError:
        safe = _normalise(os.path.basename(filename)) or "upload"
        return [Entry(safe, os.path.getsize(path), lambda: open(path, "rb"))], lambda: None, False
    entries = []
    for member in tf.getmembers():
        if member.isfile() and (name := _normalise(member.name)) is not None:
            entries.append(Entry(name, member.size, lambda m=member: tf.extractfile(m)))
    return entries, tf.close, True


def _plan_dir(layout: WorldLayout, entries: list[Entry], name: str) -> list[tuple[Entry, str]]:
    names = {e.name for e in entries}
    roots = [posixpath.dirname(e.name) for e in entries if posixpath.basename(e.name) == layout.marker]
    if not roots:
        raise BackupError(f"No world found: the archive has no {layout.marker}.")
    depth = min(r.count("/") + (1 if r else 0) for r in roots)
    roots = sorted({r for r in roots if r.count("/") + (1 if r else 0) == depth})
    for root in roots:
        prefix = root + "/" if root else ""
        if any(prefix + p not in names for p in layout.requires) or any(prefix + p in names for p in layout.forbids):
            raise BackupError("This world is for the other Minecraft edition.")
    by_base = {posixpath.basename(r): r for r in roots}
    if name in by_base:
        primary = by_base[name]
    elif len(roots) == 1:
        primary = roots[0]
    else:
        plain = [b for b in by_base if not b.endswith(("_nether", "_the_end"))]
        if len(plain) != 1:
            raise BackupError(f"The archive holds several worlds ({', '.join(by_base)}); keep only one.")
        primary = by_base[plain[0]]
    base = posixpath.basename(primary)
    targets = {primary: name}
    for suffix in ("_nether", "_the_end"):
        if base + suffix in by_base:
            targets[by_base[base + suffix]] = name + suffix
    files = []
    for entry in entries:
        for root, dest in targets.items():
            prefix = root + "/" if root else ""
            if entry.name.startswith(prefix):
                files.append((entry, dest + "/" + entry.name[len(prefix):]))
                break
    return files


def _plan_files(layout: WorldLayout, entries: list[Entry], name: str, whole: Optional[Entry]) -> list[tuple[Entry, str]]:
    taken = [whole] if whole is not None else [e for e in entries if e.name.lower().endswith(layout.exts)]
    if not taken:
        raise BackupError(f"No save file found: expected {', '.join(layout.exts)}.")
    # A save and its backup copies share a name once the copy suffix is stripped; the save itself wins.
    saves: dict[str, dict[str, list[Entry]]] = {}
    for e in taken:
        stem = os.path.splitext(posixpath.basename(e.name))[0]
        own = re.sub(layout.strip, "", stem) if layout.strip else stem
        saves.setdefault(own, {}).setdefault(stem, []).append(e)
    chosen: dict[str, list[Entry]] = {}
    for own, copies in saves.items():
        if len(copies) > 1 and own not in copies:
            raise BackupError(f"The archive holds several copies of {own}; keep only one.")
        chosen[own] = copies[own] if own in copies else next(iter(copies.values()))
    for own, files in chosen.items():
        exts = {os.path.splitext(e.name)[1].lower() for e in files}
        if layout.complete and not set(layout.complete) <= exts:
            raise BackupError(f"{own} is incomplete: a save needs {' and '.join(layout.complete)}.")
    if layout.rename and name:
        if name in chosen:
            chosen = {name: chosen[name]}
        elif len(chosen) == 1:
            chosen = {name: next(iter(chosen.values()))}
    if layout.nest and len(chosen) != 1:
        raise BackupError(f"Upload the save of one map (found {len(chosen)}).")
    result = []
    for own, files in chosen.items():
        for e in files:
            dest = own + os.path.splitext(e.name)[1]
            result.append((e, f"{own}/{dest}" if layout.nest else dest))
    return result


def plan_upload(world: World, path: str, filename: str) -> Plan:
    """Work out which entries of the file make up the world and where they go. Raises BackupError."""
    layout = world.layout
    entries, close, is_archive = open_upload(path, filename)
    try:
        if layout.kind == "dir":
            if not is_archive:
                raise BackupError("Use an archive of the world folder, not a single file.")
            files = _plan_dir(layout, entries, world.name)
        else:
            whole = None
            if not is_archive or (layout.self_marker and any(posixpath.basename(e.name) == layout.self_marker for e in entries)):
                ext = os.path.splitext(filename)[1].lower()
                if ext not in layout.exts:
                    raise BackupError(f"Expected {', '.join(layout.exts)} or an archive of them.")
                safe = _normalise(os.path.basename(filename)) or ("save" + ext)
                whole = Entry(safe, os.path.getsize(path), lambda: open(path, "rb"))
            files = _plan_files(layout, entries, world.name, whole)
    except BaseException:
        close()
        raise
    tops = sorted({dest.split("/", 1)[0] for _, dest in files})
    summary = f"{len(files)} files, {', '.join(tops[:3])}{'…' if len(tops) > 3 else ''}"
    return Plan(files, summary, close)


def tar_stream(files: list[tuple[Entry, str]]) -> Iterator[bytes]:
    """The chosen entries as one uncompressed tar, member by member, without holding a file in memory.
    mtime is now: Factorio and Satisfactory load their newest save."""
    now = int(time.time())
    for entry, dest in files:
        info = tarfile.TarInfo(dest)
        info.size, info.mtime, info.mode = entry.size, now, 0o644
        yield info.tobuf(tarfile.PAX_FORMAT, "utf-8", "surrogateescape")
        remaining = entry.size
        with entry.open() as f:
            while remaining > 0:
                chunk = f.read(min(CHUNK, remaining))
                if not chunk:
                    raise BackupError(f"{entry.name} ended early; the archive is damaged.")
                remaining -= len(chunk)
                yield chunk
        if pad := -entry.size % 512:
            yield b"\0" * pad
    yield b"\0" * 1024


# ---- shell scripts (POSIX sh, GNU and busybox) -------------------------------------------------------------

# Owner of the first existing ancestor of $1, as uid:gid.
_OWNER = 'own() { p="$1"; while [ ! -e "$p" ]; do p=$(dirname "$p"); done; stat -c %u:%g "$p"; }'

# D: newline separated folders; G: data directory, whose *backup* folders are searched too.
LIST = r'''{ printf '%s\n' "$D"; [ -d "$G" ] && find "$G" -mindepth 1 -maxdepth 2 -type d -iname '*backup*'; } | sort -u |
while IFS= read -r d; do
  [ -n "$d" ] && [ -d "$d" ] || continue
  echo "dir $d"
  find "$d" -maxdepth 2 -type f | while IFS= read -r f; do stat -c 'file %s %Y %n' "$f"; done
done; exit 0'''

# T target, B copies dir, F file name. A dir target is archived with its Paper companions.
SNAPSHOT = f'''set -e; {_OWNER}
mkdir -p "$B"; o=$(own "$T")
if [ "$K" = dir ]; then
  [ -d "$T" ] || {{ echo "world folder $T does not exist"; exit 3; }}
  P=$(dirname "$T"); W=$(basename "$T"); set -- "$W"
  for x in "$T"_nether "$T"_the_end; do [ -d "$x" ] && set -- "$@" "$(basename "$x")"; done
  tar -C "$P" -czf "$B/$F.part" "$@"
else
  [ -d "$T" ] || {{ echo "save folder $T does not exist"; exit 3; }}
  tar -C "$T" -czf "$B/$F.part" .
fi
mv "$B/$F.part" "$B/$F"; chown "$o" "$B" "$B/$F"'''

# S staging (filled by put_archive, or from a GameFleet copy A), T target, K kind.
RESTORE = f'''set -e; {_OWNER}
if [ -n "$A" ]; then rm -rf "$S"; mkdir -p "$S"; tar -xzf "$A" -C "$S"; fi
if [ "$K" = dir ]; then
  P=$(dirname "$T"); W=$(basename "$T"); o=$(own "$P")
  if [ ! -d "$S/$W" ]; then n=0; for d in "$S"/*/; do [ -d "$d" ] && {{ n=$((n+1)); only="$d"; }}; done; [ "$n" = 1 ] && mv "$only" "$S/$W"; fi
  [ -d "$S/$W" ] || {{ echo "no world folder in the backup"; exit 3; }}
  chown -R "$o" "$S"; mkdir -p "$P"
  for d in "$S"/*/; do d=${{d%/}}; n=$(basename "$d"); rm -rf "$P/$n.gamefleet-old"
    [ -e "$P/$n" ] && mv "$P/$n" "$P/$n.gamefleet-old"; mv "$d" "$P/$n"; rm -rf "$P/$n.gamefleet-old"; done
else
  o=$(own "$T"); chown -R "$o" "$S"; mkdir -p "$T"
  (cd "$S" && find . -type f) | while IFS= read -r f; do mkdir -p "$T/$(dirname "$f")"; mv -f "$S/$f" "$T/$f"; done
fi
rm -rf "$S"'''

MKDIR = 'rm -rf "$S"; mkdir -p "$S"'


# ---- service ----------------------------------------------------------------------------------------------

class BackupService:
    def __init__(self) -> None:
        self.jobs: dict[str, BackupJob] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    # ---- resolving ----

    async def world(self, server: GameServer) -> World:
        """Where the world of this server lives; BackupError explains why it cannot be restored."""
        layout = LAYOUTS.get(GameServerType(server.game))
        if layout is None:
            raise BackupError("Restoring backups is not supported for this game yet.")
        if not server.data_path or not server.world_path:
            raise BackupError("GameFleet does not know where this server keeps its world (unknown image).")
        try:
            attrs = await docker_service.inspect(server.container_name)
        except docker.errors.NotFound:
            raise BackupError("The container does not exist.")
        env = {}
        for entry in (attrs.get("Config") or {}).get("Env") or []:
            key, _, value = entry.partition("=")
            env[key] = value
        name = next((env[k] for k in layout.name_env if env.get(k)), "")
        if not name and layout.name_property:
            text = await docker_service.read_file(server.container_name, f"{server.data_path}/server.properties")
            for line in (text or "").splitlines():
                key, sep, value = line.partition("=")
                if sep and key.strip() == layout.name_property and value.strip():
                    name = value.strip()
        name = name or layout.default_name
        fill = dict(data=server.data_path, world=server.world_path, name=name)
        target = layout.target.format(**fill)
        mounts = [m.get("Destination", "").rstrip("/") for m in attrs.get("Mounts") or [] if m.get("Destination")]
        mounted = lambda path: any(path == m or path.startswith(m + "/") for m in mounts)  # noqa: E731
        if not mounted(target):
            raise BackupError(f"{target} is not on a volume or bind mount of the container.")
        copies = f"{server.data_path}/{COPY_DIR}"
        sources = [p for p in (s.format(**fill) for s in layout.sources) if mounted(p)] + [copies]
        return World(server, layout, name, target, copies, sources, bool((attrs.get("State") or {}).get("Running")))

    async def info(self, server: GameServer) -> BackupInfo:
        job = self.jobs.get(server.id)
        try:
            world = await self.world(server)
        except BackupError as exc:
            return BackupInfo(supported=False, reason=str(exc), job=job)
        locations, backups = await self.list(world)
        return BackupInfo(
            supported=True, world=world.name or posixpath.basename(world.target), target=world.target,
            kind=world.layout.kind, accept=world.layout.accept, hint=world.layout.hint, running=world.running,
            locations=locations, backups=backups, job=job,
        )

    # ---- shell access ----

    @asynccontextmanager
    async def _shell(self, world: World) -> AsyncIterator[Callable]:
        """Run scripts inside the game container while it runs, else in a helper that shares its mounts."""
        name = world.server.container_name
        running = (await docker_service.inspect(name)).get("State", {}).get("Running")
        helper = None if running else await docker_service.create_helper(name)
        try:
            async def run(script: str, **env: str) -> str:
                code, output = await docker_service.shell(helper or name, script, env)
                if code != 0:
                    raise BackupError(output.strip().splitlines()[-1] if output.strip() else f"script failed ({code})")
                return output
            yield run
        finally:
            if helper:
                await docker_service.remove_container(helper)

    async def list(self, world: World) -> tuple[list[str], list[Backup]]:
        """The folders searched and the backups in them that this game can restore, newest first."""
        async with self._shell(world) as run:
            output = await run(LIST, D="\n".join(world.sources), G=world.server.data_path)
        pattern = re.compile(world.layout.backup_files, re.I)
        data = world.server.data_path.rstrip("/") + "/"
        locations: list[str] = []
        backups: dict[str, Backup] = {}
        for line in output.splitlines():
            if line.startswith("dir "):
                locations.append(line[4:])
                continue
            parts = line.split(" ", 3)
            if len(parts) != 4 or parts[0] != "file" or not (parts[1].isdigit() and parts[2].isdigit()):
                continue
            path = parts[3]
            file = posixpath.basename(path)
            if path in backups or not pattern.search(file) or file.endswith(".part"):
                continue
            folder = posixpath.dirname(path)
            backups[path] = Backup(
                path=path, file=file, folder=folder[len(data):] if folder.startswith(data) else folder,
                size=int(parts[1]), created=int(parts[2]), gamefleet=folder == world.copies,
            )
        return locations, sorted(backups.values(), key=lambda b: b.created, reverse=True)

    async def find(self, world: World, path: str) -> Backup:
        """The listed backup at `path`; nothing outside the backup folders can be read or restored."""
        for backup in (await self.list(world))[1]:
            if backup.path == path:
                return backup
        raise BackupError("Backup not found.")

    async def download(self, world: World, path: str) -> tuple[Iterator[bytes], int]:
        """The backup's bytes and size, unwrapped from Docker's tar stream."""
        backup = await self.find(world, path)
        stream, stat = await docker_service.get_archive(world.server.container_name, backup.path)

        def unwrap() -> Iterator[bytes]:
            with tarfile.open(fileobj=_ChunkReader(stream), mode="r|") as tar:
                member = tar.next()
                f = tar.extractfile(member) if member else None
                while f and (chunk := f.read(CHUNK)):
                    yield chunk
        return unwrap(), int(stat.get("size") or 0)

    async def _fetch(self, world: World, path: str) -> str:
        """Copy a backup out of the container into a temporary file here."""
        stream, _ = await docker_service.get_archive(world.server.container_name, path)

        def copy() -> str:
            out = tempfile.NamedTemporaryFile(prefix="gamefleet-restore-", delete=False)
            try:
                with out, tarfile.open(fileobj=_ChunkReader(stream), mode="r|") as tar:
                    member = tar.next()
                    f = tar.extractfile(member) if member else None
                    if f is None:
                        raise BackupError("The backup could not be read.")
                    while chunk := f.read(CHUNK):
                        out.write(chunk)
            except BaseException:
                os.unlink(out.name)
                raise
            return out.name
        return await asyncio.to_thread(copy)

    # ---- jobs ----

    def _start(self, server: GameServer, job: BackupJob, coro) -> BackupJob:
        current = self.jobs.get(server.id)
        if current and current.finished_at is None:
            coro.close()
            raise BackupError("A restore is already running for this server.")
        self.jobs[server.id] = job

        async def guarded():
            try:
                await coro
                job.phase = "done"
            except BackupError as exc:
                job.phase, job.error = "failed", str(exc)
            except Exception as exc:
                log.exception("Restore failed for %s", server.container_name)
                job.phase, job.error = "failed", f"{type(exc).__name__}: {exc}"
            finally:
                job.finished_at = time.time()
                docker_service.forget(server.container_name)
        self._tasks[server.id] = asyncio.create_task(guarded())
        return job

    def restore_upload(self, world: World, plan: Plan, path: str, keep_copy: bool, filename: str) -> BackupJob:
        job = BackupJob(source=filename, phase="stopping", started_at=time.time())
        return self._start(world.server, job, self._restore(world, job, keep_copy, plan=plan, path=path))

    def restore_backup(self, world: World, backup: Backup, keep_copy: bool) -> BackupJob:
        job = BackupJob(source=backup.file, phase="stopping" if backup.gamefleet else "preparing", started_at=time.time())
        return self._start(world.server, job, self._restore(world, job, keep_copy, backup=backup))

    @staticmethod
    def _copy_name(world: World) -> str:
        stem = world.name if world.layout.kind == "dir" else "saves"
        stem = re.sub(r"[^A-Za-z0-9 ._-]+", "_", stem).strip(" .") or "world"
        return f"{stem}-before-restore-{time.strftime('%Y%m%d-%H%M%S')}.tar.gz"

    async def _restore(self, world: World, job: BackupJob, keep_copy: bool, plan: Optional[Plan] = None,
                       path: Optional[str] = None, backup: Optional[Backup] = None) -> None:
        name = world.server.container_name
        was_running = world.running
        touched = False
        try:
            # A copy GameFleet kept is restored as it was; anything else is copied here and checked first,
            # before the server is touched.
            own_copy = backup is not None and backup.gamefleet
            if backup is not None and not own_copy:
                path = await self._fetch(world, backup.path)
                plan = await asyncio.to_thread(plan_upload, world, path, backup.file)
            if was_running:
                job.phase = "stopping"
                await docker_service.power(name, "stop")
                world.running = False
            if keep_copy:
                job.phase = "snapshot"
                file = self._copy_name(world)
                async with self._shell(world) as run:
                    try:
                        await run(SNAPSHOT, T=world.target, B=world.copies, F=file, K=world.layout.kind)
                        job.snapshot = file
                    except BackupError as exc:
                        if "does not exist" not in str(exc):
                            raise
                        job.warning = "There was no world to keep a copy of."
            job.phase = "applying"
            staging = posixpath.join(posixpath.dirname(world.target) if world.layout.kind == "dir" else world.target, STAGING)
            async with self._shell(world) as run:
                await run(MKDIR, S=staging)
                if plan is not None:
                    await docker_service.put_archive(name, staging, tar_stream(plan.files))
                touched = True
                await run(RESTORE, S=staging, T=world.target, K=world.layout.kind, A=backup.path if own_copy else "")
            if was_running:
                job.phase = "starting"
                await docker_service.power(name, "start")
                job.restarted = True
        except BaseException:
            # Nothing was replaced yet: bring the server back as it was. Otherwise leave it stopped for a look.
            if was_running and not touched and not world.running:
                try:
                    await docker_service.power(name, "start")
                    job.restarted = True
                except Exception as exc:
                    log.warning("Could not restart %s after a failed restore: %s", name, exc)
            raise
        finally:
            if plan is not None:
                plan.cleanup()
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass


class _ChunkReader:
    """File-like read() over Docker's chunk generator, for tarfile's stream mode. Reads advance an offset into
    the current chunk, so small reads from multi-GB streams never copy more than they return."""

    def __init__(self, chunks: Iterator[bytes]) -> None:
        self._chunks, self._buf, self._pos = iter(chunks), b"", 0

    def read(self, n: int = -1) -> bytes:
        parts: list[bytes] = []
        while n != 0:
            if self._pos >= len(self._buf):
                try:
                    self._buf, self._pos = next(self._chunks), 0
                except StopIteration:
                    break
                continue
            take = len(self._buf) - self._pos if n < 0 else min(n, len(self._buf) - self._pos)
            parts.append(self._buf[self._pos:self._pos + take])
            self._pos += take
            if n > 0:
                n -= take
        return b"".join(parts)


backup_service = BackupService()
