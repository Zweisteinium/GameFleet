from fastapi import APIRouter, HTTPException
import docker.errors

from gamefleet_backend.models.container_info import ContainerInfo
from gamefleet_backend.services.docker_service import DockerService

router = APIRouter()


def _get_service() -> DockerService:
    try:
        return DockerService()
    except docker.errors.DockerException as e:
        raise HTTPException(status_code=503, detail=f"Docker daemon unavailable: {e}")


@router.get("/containers", response_model=list[ContainerInfo])
def list_all_containers():
    """List every container on the host regardless of state."""
    return _get_service().get_all_containers()


@router.get("/containers/managed", response_model=list[ContainerInfo])
def list_managed_containers():
    """List only containers labelled gamefleet.managed=true."""
    return _get_service().get_managed_containers()
