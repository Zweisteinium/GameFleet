from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from gamefleet_backend.db.models.host_settings import HostSettingsBase
from gamefleet_backend.db.session import get_session
from gamefleet_backend.models.template import CreateJob, CreatePreview, CreateRequest, Template
from gamefleet_backend.services.create_service import create_service
from gamefleet_backend.services.game_server_service import GameServerService
from gamefleet_backend.services.modpack_service import modrinth
from gamefleet_backend.services.settings_service import load_settings
from gamefleet_backend.services.template_service import TemplateError, templates

router = APIRouter()


class ModrinthPack(BaseModel):
    slug: str
    title: str
    description: str = ""
    icon_url: Optional[str] = None
    downloads: int = 0
    versions: list[str] = []  # Minecraft versions


async def _settings(session: AsyncSession) -> HostSettingsBase:
    # A detached copy: a job outlives the request's session.
    return HostSettingsBase.model_validate((await load_settings(session)).model_dump())


@router.get("/templates", response_model=list[Template], operation_id="getTemplates")
def get_templates():
    """The games GameFleet can create servers for."""
    return list(templates().values())


@router.post("/preview", response_model=CreatePreview, operation_id="previewCreate")
async def preview(body: CreateRequest, session: AsyncSession = Depends(get_session)):
    """The files a request would write and anything that stops it, without changing anything."""
    try:
        result, _, _ = await create_service.preview(body, await _settings(session), GameServerService(session))
    except TemplateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result


@router.post("", response_model=CreateJob, operation_id="createServer")
async def create(body: CreateRequest, session: AsyncSession = Depends(get_session)):
    """Create the server in the background; follow it with /jobs/{id}."""
    settings = await _settings(session)
    try:
        result, rendered, template = await create_service.preview(body, settings, GameServerService(session))
    except TemplateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result.problems or rendered is None:
        raise HTTPException(status_code=409, detail=" ".join(result.problems))
    return create_service.start(body, template, rendered, settings)


@router.get("/jobs/{job_id}", response_model=CreateJob, operation_id="getCreateJob")
def get_job(job_id: str):
    job = create_service.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job (GameFleet was restarted?)")
    return job


@router.get("/minecraft-versions", response_model=list[str], operation_id="getMinecraftVersions")
async def minecraft_versions():
    return await create_service.minecraft_versions()


@router.get("/modrinth-packs", response_model=list[ModrinthPack], operation_id="searchModrinthPacks")
async def modrinth_packs(q: str = Query(min_length=2, max_length=100)):
    """Modpacks on Modrinth for the create wizard."""
    return [ModrinthPack(slug=h["slug"], title=h.get("title") or h["slug"], description=h.get("description") or "",
                         icon_url=h.get("icon_url") or None, downloads=h.get("downloads") or 0,
                         versions=h.get("versions") or [])
            for h in await modrinth.search_modpacks(q) if h.get("slug")]
