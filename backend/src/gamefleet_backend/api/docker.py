from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gamefleet_backend.db.models.game_server import GameServerPublic
from gamefleet_backend.dependencies import get_docker_discovery_service
from gamefleet_backend.models.container_info import ContainerInfo, DiscoveredContainer, DockerStatus
from gamefleet_backend.models.game_server_type import GameServerType
from gamefleet_backend.services.docker_discovery_service import AUTO_IMPORT, DockerDiscoveryService
from gamefleet_backend.services.docker_service import DockerUnavailable, SERVER_ADDRESS, docker_service, map_container

router = APIRouter()


class ImportRequest(BaseModel):
    container_name: str
    # Override the detected game (for keyword/port guesses) or the display name.
    game: Optional[GameServerType] = None
    name: Optional[str] = None


def _unavailable(exc: DockerUnavailable) -> HTTPException:
    return HTTPException(status_code=503, detail=f"Docker daemon unavailable: {exc}")


@router.get("/status", response_model=DockerStatus, operation_id="getDockerStatus")
async def docker_status():
    """Whether the backend can talk to the Docker daemon (needs /var/run/docker.sock mounted)."""
    available, error = await docker_service.status()
    return DockerStatus(available=available, error=error, auto_import=AUTO_IMPORT, address=SERVER_ADDRESS)


@router.get("/containers", response_model=list[ContainerInfo], operation_id="getContainers")
async def list_containers():
    """Every container on the host, regardless of state."""
    try:
        return [map_container(c) for c in await docker_service.list_raw()]
    except DockerUnavailable as exc:
        raise _unavailable(exc)


@router.get("/discovered", response_model=list[DiscoveredContainer], operation_id="getDiscoveredContainers")
async def discovered(service: DockerDiscoveryService = Depends(get_docker_discovery_service)):
    """Containers that look like game servers, with the server they are linked to (if imported).
    Calling this also imports labelled and well-known containers."""
    try:
        return await service.discover()
    except DockerUnavailable as exc:
        raise _unavailable(exc)


@router.post("/import", response_model=GameServerPublic, operation_id="importContainer")
async def import_container(body: ImportRequest, service: DockerDiscoveryService = Depends(get_docker_discovery_service)):
    """Import a discovered container as a server (or re-sync an already imported one)."""
    try:
        raw = await docker_service.get_raw(body.container_name)
    except DockerUnavailable as exc:
        raise _unavailable(exc)
    if raw is None:
        raise HTTPException(status_code=404, detail="Container not found")
    try:
        server = await service.import_container(raw, game=body.game, name=body.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return GameServerPublic.from_server(server)


@router.put("/ignored/{container_name}", operation_id="ignoreContainer")
async def ignore_container(container_name: str, service: DockerDiscoveryService = Depends(get_docker_discovery_service)):
    """Hide a container from discovery."""
    await service.set_ignored(container_name, True)
    return {"container_name": container_name, "ignored": True}


@router.delete("/ignored/{container_name}", operation_id="unignoreContainer")
async def unignore_container(container_name: str, service: DockerDiscoveryService = Depends(get_docker_discovery_service)):
    """Show a hidden container in discovery again."""
    await service.set_ignored(container_name, False)
    return {"container_name": container_name, "ignored": False}
