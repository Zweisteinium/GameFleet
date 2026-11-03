from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from gamefleet_backend.db.models.host_settings import HostSettingsBase
from gamefleet_backend.db.session import get_session
from gamefleet_backend.services.settings_service import load_settings, save_settings, servers_dir_problem

router = APIRouter()


class SettingsView(HostSettingsBase):
    # Why servers cannot be created with these settings (None: they can).
    servers_dir_problem: Optional[str] = None


async def _view(settings: HostSettingsBase) -> SettingsView:
    return SettingsView(**settings.model_dump(), servers_dir_problem=await servers_dir_problem(settings))


@router.get("", response_model=SettingsView, operation_id="getSettings")
async def get_settings(session: AsyncSession = Depends(get_session)):
    """Settings of this GameFleet installation and whether new servers can be created with them."""
    return await _view(await load_settings(session))


@router.put("", response_model=SettingsView, operation_id="updateSettings")
async def update_settings(body: HostSettingsBase, session: AsyncSession = Depends(get_session)):
    return await _view(await save_settings(session, body))
