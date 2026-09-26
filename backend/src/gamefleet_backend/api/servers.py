import asyncio
import os
import tempfile
from typing import Literal, Sequence
from urllib.parse import quote

import docker.errors
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from gamefleet_backend.auth import current_user, download_user, is_admin
from gamefleet_backend.db.models.game_server import GameServer, GameServerPublic
from gamefleet_backend.dependencies import get_docker_discovery_service, get_game_server_service
from gamefleet_backend.models.container_info import HostStats
from gamefleet_backend.models.game_server_type import GAME_CATALOG, GameServerType, QueryProtocol
from gamefleet_backend.models.server_info import LiveServerInfo
from gamefleet_backend.services.backup_service import (
    BackupError, BackupInfo, BackupJob, World, backup_service, plan_upload,
)
from gamefleet_backend.services.docker_discovery_service import DockerDiscoveryService
from gamefleet_backend.services.docker_service import DockerUnavailable, docker_service
from gamefleet_backend.services.game_server_service import GameServerService
from gamefleet_backend.services.live_server_info_service import LiveServerInfoService
from gamefleet_backend.services.modpack_service import manual_fields


router = APIRouter()
# Everything that changes data or touches the host needs a login.
LOGIN = [Depends(current_user)]


class GameServerCreate(BaseModel):
    name: str
    game: GameServerType
    address: str
    port: int = Field(ge=1, le=65535)
    query_port: int | None = Field(default=None, ge=1, le=65535)
    rcon_port: int | None = Field(default=None, ge=1, le=65535)
    rcon_password: str | None = None
    is_public: bool = False
    # Typed by the user; Docker-linked servers detect their pack on their own.
    modpack_name: str | None = Field(default=None, max_length=200)
    modpack_url: str | None = Field(default=None, max_length=500)


class GameServerUpdate(BaseModel):
    name: str | None = None
    game: GameServerType | None = None
    address: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    query_port: int | None = Field(default=None, ge=1, le=65535)
    rcon_port: int | None = Field(default=None, ge=1, le=65535)
    rcon_password: str | None = None
    is_public: bool | None = None
    # An empty name clears a typed pack and lets detection fill it in again.
    modpack_name: str | None = Field(default=None, max_length=200)
    modpack_url: str | None = Field(default=None, max_length=500)


class PowerRequest(BaseModel):
    action: Literal["start", "stop", "restart"]
    # On start: stop the servers that hold this server's host ports instead of answering 409.
    stop_conflicting: bool = False


class PortConflict(BaseModel):
    container_name: str
    ports: list[str]  # "25565/tcp"
    # The GameFleet server behind the container; only those can be stopped from here.
    server_id: str | None = None
    server_name: str | None = None


class PowerConflictDetail(BaseModel):
    message: str
    conflicts: list[PortConflict]


class PowerConflict(BaseModel):
    detail: PowerConflictDetail


class GameTypeInfo(BaseModel):
    type: GameServerType
    label: str
    protocol: QueryProtocol
    default_port: int
    default_query_port: int | None
    default_rcon_port: int | None
    needs_rcon: bool


def _visible(servers: Sequence[GameServer], admin: bool) -> list[GameServer]:
    return [s for s in servers if admin or s.is_public]


async def _visible_server(server_id: str, admin: bool, service: GameServerService) -> GameServer:
    """The server, or 404 when it does not exist or is hidden from the caller (no hint that it exists)."""
    server = await service.get_server_by_id(server_id)
    if not server or not (admin or server.is_public):
        raise HTTPException(status_code=404, detail="Server not found")
    return server


@router.get('', response_model=Sequence[GameServerPublic], operation_id="getServers")
async def get_servers(
    admin: bool = Depends(is_admin),
    service: GameServerService = Depends(get_game_server_service)
):
    """Get the game servers the caller may see: all of them when logged in, the public ones otherwise."""
    return [GameServerPublic.from_server(s, admin) for s in _visible(await service.get_all_servers(), admin)]


@router.post('', response_model=GameServerPublic, operation_id="postServer", dependencies=LOGIN)
async def post_server(
    server_data: GameServerCreate,
    service: GameServerService = Depends(get_game_server_service)
):
    """Create a new game server."""
    data = server_data.model_dump()
    data.update(await manual_fields(data.pop("modpack_name"), data.pop("modpack_url")))
    return GameServerPublic.from_server(await service.create_server(data))


@router.get("/supported_types", response_model=Sequence[GameServerType], operation_id="getSupportedServerTypes")
def supported_types() -> list[GameServerType]:
    """Get list of supported game server types."""
    return list(GameServerType)


@router.get("/game-types", response_model=Sequence[GameTypeInfo], operation_id="getGameTypes")
def game_types() -> list[GameTypeInfo]:
    """Get supported game types with display labels and default ports (for forms)."""
    return [
        GameTypeInfo(
            type=game,
            label=spec.label,
            protocol=spec.protocol,
            default_port=spec.default_port,
            default_query_port=spec.resolve_query_port(spec.default_port, None) if spec.protocol == QueryProtocol.a2s else None,
            default_rcon_port=spec.default_rcon_port,
            needs_rcon=spec.protocol == QueryProtocol.factorio_rcon,
        )
        for game, spec in GAME_CATALOG.items()
    ]


@router.get('/live-info', response_model=dict[str, LiveServerInfo], operation_id="getAllServersLiveInfo")
async def get_all_servers_live_info(
    admin: bool = Depends(is_admin),
    service: GameServerService = Depends(get_game_server_service)
):
    """Get live information for every visible server at once (queried concurrently)."""
    servers = _visible(await service.get_all_servers(), admin)
    return await LiveServerInfoService.get_all_server_info(servers)


@router.get('/host-stats', response_model=dict[str, HostStats], operation_id="getAllHostStats", dependencies=LOGIN)
async def get_all_host_stats(
    service: GameServerService = Depends(get_game_server_service)
):
    """Container state and resource usage for every Docker-linked server (cached per container)."""
    servers = [s for s in await service.get_all_servers() if s.source == "docker" and s.container_name]
    if not servers:
        return {}
    try:
        await docker_service.status()
        results = await asyncio.gather(*(docker_service.host_stats(s.container_name, s.data_path, s.world_path) for s in servers))
    except DockerUnavailable:
        return {}
    return {server.id: stats for server, stats in zip(servers, results)}


@router.get('/by-type/{server_type}', response_model=Sequence[GameServerPublic], operation_id="getServersByType")
async def get_servers_by_type(
    server_type: GameServerType,
    admin: bool = Depends(is_admin),
    service: GameServerService = Depends(get_game_server_service)
):
    """Get the visible servers of a specific game type."""
    servers = _visible(await service.get_servers_by_type(server_type), admin)
    return [GameServerPublic.from_server(s, admin) for s in servers]


@router.get('/{server_id}', response_model=GameServerPublic, operation_id="getServerById")
async def get_server(
    server_id: str,
    admin: bool = Depends(is_admin),
    service: GameServerService = Depends(get_game_server_service)
):
    """Get a specific game server by ID."""
    return GameServerPublic.from_server(await _visible_server(server_id, admin, service), admin)


@router.put('/{server_id}', response_model=GameServerPublic, operation_id="updateServer", dependencies=LOGIN)
async def update_server(
    server_id: str,
    server_data: GameServerUpdate,
    service: GameServerService = Depends(get_game_server_service)
):
    """Update an existing game server (only fields that are sent are changed)."""
    update_data = server_data.model_dump(exclude_unset=True)
    if "modpack_name" in update_data or "modpack_url" in update_data:
        current = await service.get_server_by_id(server_id)
        typed = (update_data.pop("modpack_name", None), update_data.pop("modpack_url", None))
        # The form sends back what it was given: only a change makes the pack a manual one.
        blank = lambda pair: tuple((value or "").strip() for value in pair)  # noqa: E731
        if current and blank(typed) != blank((current.modpack_name, current.modpack_url)):
            update_data.update(await manual_fields(*typed))
    server = await service.update_server(server_id, update_data)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    return GameServerPublic.from_server(server)


@router.delete('/{server_id}', operation_id="deleteServer", dependencies=LOGIN)
async def delete_server(
    server_id: str,
    service: GameServerService = Depends(get_game_server_service),
    discovery: DockerDiscoveryService = Depends(get_docker_discovery_service),
):
    """Delete a game server. A Docker-linked server's container is hidden from discovery afterwards."""
    server = await service.get_server_by_id(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    if server.source == "docker" and server.container_name:
        # Otherwise discovery would offer (or re-import) the container right away.
        await discovery.set_ignored(server.container_name, True)
        docker_service.forget(server.container_name)
    await service.delete_server(server_id)
    return {"message": "Server deleted successfully"}


async def _docker_server(server_id: str, service: GameServerService) -> GameServer:
    server = await service.get_server_by_id(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    if server.source != "docker" or not server.container_name:
        raise HTTPException(status_code=409, detail="This server is not linked to a Docker container")
    return server


@router.get('/{server_id}/host', response_model=HostStats, operation_id="getServerHostStats", dependencies=LOGIN)
async def get_server_host_stats(
    server_id: str,
    service: GameServerService = Depends(get_game_server_service)
):
    """Container state, CPU, memory and data sizes of a Docker-linked server."""
    server = await _docker_server(server_id, service)
    try:
        return await docker_service.host_stats(server.container_name, server.data_path, server.world_path)
    except DockerUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Docker daemon unavailable: {exc}")


async def _free_ports(server: GameServer, stop_conflicting: bool, service: GameServerService) -> None:
    """Instances of one game usually share a host port, so only one of them can run. Before a start, find the
    running containers that hold this server's ports: answer 409 with them, or stop them when asked to."""
    held = await docker_service.port_conflicts(server.container_name)
    if not held:
        return
    linked = {s.container_name: s for s in await service.get_all_servers() if s.source == "docker"}
    conflicts = [
        PortConflict(container_name=name, ports=ports, server_id=getattr(linked.get(name), "id", None),
                     server_name=getattr(linked.get(name), "name", None))
        for name, ports in held.items()
    ]
    foreign = [c.container_name for c in conflicts if c.server_id is None]
    if stop_conflicting and not foreign:
        for conflict in conflicts:
            await docker_service.power(conflict.container_name, "stop")
            docker_service.forget(conflict.container_name)
        return
    ports = ", ".join(sorted({p for c in conflicts for p in c.ports}))
    holders = ", ".join(f"{c.server_name} ({c.container_name})" if c.server_name else c.container_name for c in conflicts)
    message = f"Port {ports} is in use by {holders}."
    if foreign:
        message += f" {', '.join(foreign)} is not a GameFleet server and has to be stopped on the host."
    raise HTTPException(status_code=409, detail=PowerConflictDetail(message=message, conflicts=conflicts).model_dump())


@router.post('/{server_id}/power', response_model=HostStats, operation_id="powerServer", dependencies=LOGIN,
             responses={409: {"model": PowerConflict, "description": "A host port is held by another container"}})
async def power_server(
    server_id: str,
    body: PowerRequest,
    service: GameServerService = Depends(get_game_server_service)
):
    """Start, stop or restart the container behind a Docker-linked server. A start answers 409 with the
    containers that hold its host ports; repeat it with `stop_conflicting` to stop those servers first."""
    server = await _docker_server(server_id, service)
    job = backup_service.jobs.get(server_id)
    if job and job.finished_at is None:
        # The job stops and starts the container itself; a start in between would load a half-restored world.
        raise HTTPException(status_code=409, detail=f"A {job.action} is running; wait until it has finished.")
    try:
        if body.action == "start":
            await _free_ports(server, body.stop_conflicting, service)
        await docker_service.power(server.container_name, body.action)
    except DockerUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Docker daemon unavailable: {exc}")
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found")
    except docker.errors.APIError as exc:
        reason = str(exc.explanation or exc)
        if "already allocated" in reason or "address already in use" in reason:
            # Not held by a container (those are caught above): a process on the host owns the port.
            detail = PowerConflictDetail(message=f"A port of this server is already in use on the host: {reason}", conflicts=[])
            raise HTTPException(status_code=409, detail=detail.model_dump())
        raise HTTPException(status_code=502, detail=f"Docker refused the request: {reason}")
    docker_service.forget(server.container_name)
    return await docker_service.host_stats(server.container_name, server.data_path, server.world_path)


@router.get('/{server_id}/live-info', response_model=LiveServerInfo, operation_id="getServerLiveInfoById")
async def get_server_live_info_by_id(
    server_id: str,
    admin: bool = Depends(is_admin),
    service: GameServerService = Depends(get_game_server_service)
):
    """Get live information for a server by its database ID."""
    return await LiveServerInfoService.get_server_info(await _visible_server(server_id, admin, service))


# ---- backups (Docker-linked servers, login required) ----------------------------------------------------

class RestoreRequest(BaseModel):
    # A backup from the listing, identified by its path inside the container.
    path: str
    # Keep a copy of the current world before it is replaced.
    keep_copy: bool = True


async def _world(server_id: str, service: GameServerService) -> World:
    server = await _docker_server(server_id, service)
    try:
        return await backup_service.world(server)
    except BackupError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except DockerUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Docker daemon unavailable: {exc}")


def _backup_error(exc: Exception) -> HTTPException:
    if isinstance(exc, BackupError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, DockerUnavailable):
        return HTTPException(status_code=503, detail=f"Docker daemon unavailable: {exc}")
    return HTTPException(status_code=502, detail=f"Docker refused the request: {getattr(exc, 'explanation', None) or exc}")


@router.get('/{server_id}/backups', response_model=BackupInfo, operation_id="getBackups", dependencies=LOGIN)
async def get_backups(server_id: str, service: GameServerService = Depends(get_game_server_service)):
    """The backups the server (or its mods) wrote, where the world they restore into lives, and the current job."""
    server = await _docker_server(server_id, service)
    try:
        info = await backup_service.info(server)
    except (BackupError, DockerUnavailable, docker.errors.DockerException) as exc:
        raise _backup_error(exc)
    # The catalog only knows the default world folder; a world folder resolved from the container
    # (level-name "World" on many modpacks) also corrects the world size in the host panel.
    if info.kind == "dir" and info.target and info.target != server.world_path:
        await service.update_server(server.id, {"world_path": info.target})
    return info


@router.get('/{server_id}/backups/job', response_model=BackupJob | None, operation_id="getBackupJob", dependencies=LOGIN)
def get_backup_job(server_id: str):
    """The running or last finished restore of a server (in memory, cheap to poll)."""
    return backup_service.jobs.get(server_id)


@router.post('/{server_id}/backups/restore', response_model=BackupJob, operation_id="restoreBackup", dependencies=LOGIN)
async def restore_backup(server_id: str, body: RestoreRequest,
                         service: GameServerService = Depends(get_game_server_service)):
    """Restore one of the listed backups. The server is stopped while it is applied and started again
    afterwards. Runs in the background; poll the job."""
    world = await _world(server_id, service)
    try:
        backup = await backup_service.find(world, body.path)
        return backup_service.restore_backup(world, backup, body.keep_copy)
    except (BackupError, DockerUnavailable, docker.errors.DockerException) as exc:
        raise _backup_error(exc)


@router.post('/{server_id}/backups/upload', response_model=BackupJob, operation_id="restoreUpload", dependencies=LOGIN,
             openapi_extra={"requestBody": {"required": True, "content": {
                 "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}}})
async def restore_upload(
    server_id: str,
    request: Request,
    filename: str = Query(..., description="Name of the uploaded file; its extension tells the format"),
    keep_copy: bool = Query(True, description="Keep a copy of the current world before it is replaced"),
    service: GameServerService = Depends(get_game_server_service),
):
    """Replace the world with an uploaded archive or save file (raw request body), same sequence as a
    restore. Runs in the background; poll the job."""
    world = await _world(server_id, service)
    job = backup_service.jobs.get(server_id)
    if job and job.finished_at is None:
        raise HTTPException(status_code=409, detail="A restore is already running for this server.")
    upload = tempfile.NamedTemporaryFile(prefix="gamefleet-restore-", delete=False)
    try:
        async for chunk in request.stream():
            upload.write(chunk)
        upload.close()
        if os.path.getsize(upload.name) == 0:
            raise HTTPException(status_code=422, detail="The upload is empty.")
        try:
            plan = await asyncio.to_thread(plan_upload, world, upload.name, filename)
        except BackupError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        try:
            return backup_service.restore_upload(world, plan, upload.name, keep_copy, os.path.basename(filename))
        except BackupError as exc:
            plan.cleanup()
            raise _backup_error(exc)
    except BaseException:
        upload.close()
        os.unlink(upload.name)
        raise


@router.get('/{server_id}/backups/download', operation_id="downloadBackup", dependencies=[Depends(download_user)],
            response_class=StreamingResponse)
async def download_backup(server_id: str, path: str = Query(...),
                          service: GameServerService = Depends(get_game_server_service)):
    """Download one of the listed backups. Accepts the bearer token as `?token=` so a plain link works."""
    world = await _world(server_id, service)
    try:
        stream, size = await backup_service.download(world, path)
    except (BackupError, DockerUnavailable, docker.errors.DockerException) as exc:
        raise _backup_error(exc)
    name = os.path.basename(path)
    ascii_name = name.encode("ascii", "replace").decode().replace('"', "").replace("?", "_")
    headers = {"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"}
    if size:
        headers["Content-Length"] = str(size)
    return StreamingResponse(stream, media_type="application/octet-stream", headers=headers)
