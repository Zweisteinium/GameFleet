from fastapi import APIRouter, HTTPException

from gamefleet_backend.models.deploy import DeployCheck, DeployCheckResult, DeployJob, DeployRequest, DeployTemplate
from gamefleet_backend.services.deploy_service import SERVERS_ROOT, DeployError, deploy_service, templates, validate_root
from gamefleet_backend.services.docker_service import DockerUnavailable

router = APIRouter()


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, DeployError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, DockerUnavailable):
        return HTTPException(status_code=503, detail=f"Docker daemon unavailable: {exc}")
    return HTTPException(status_code=502, detail=f"Docker refused the request: {getattr(exc, 'explanation', None) or exc}")


@router.get("/templates", response_model=list[DeployTemplate], operation_id="getDeployTemplates")
def get_templates():
    """The games GameFleet can deploy, with the settings each one asks for and its default ports."""
    return templates()


@router.get("/root", operation_id="getDeployRoot")
def get_root():
    """Where new servers are created on the host, and why deploys would fail if that is unusable."""
    return {"root": SERVERS_ROOT, "problem": validate_root()}


@router.post("/check", response_model=DeployCheckResult, operation_id="checkDeploy")
async def check(body: DeployCheck):
    """Whether the name and the host ports are free before anything is created."""
    try:
        return await deploy_service.check(body.template, body.name, body.host_ports)
    except Exception as exc:
        raise _error(exc)


@router.post("", response_model=DeployJob, operation_id="deployServer")
async def deploy(body: DeployRequest):
    """Create and start a new server. Returns the job to poll; the server appears in the fleet when it is done."""
    try:
        return await deploy_service.deploy(body)
    except Exception as exc:
        raise _error(exc)


@router.get("/jobs", response_model=list[DeployJob], operation_id="getDeployJobs")
def jobs():
    return sorted(deploy_service.jobs.values(), key=lambda j: j.started_at, reverse=True)


@router.get("/jobs/{job_id}", response_model=DeployJob, operation_id="getDeployJob")
def job(job_id: str):
    found = deploy_service.jobs.get(job_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return found
