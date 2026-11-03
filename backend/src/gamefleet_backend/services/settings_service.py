"""The host settings (one row) and whether the servers folder can be used for creating servers."""
import os
import posixpath
import socket
from typing import Optional

import docker.errors
from sqlalchemy.ext.asyncio import AsyncSession

from gamefleet_backend.db.models.host_settings import HostSettings, HostSettingsBase
from gamefleet_backend.services.docker_service import DockerUnavailable, docker_service


async def load_settings(session: AsyncSession) -> HostSettings:
    settings = await session.get(HostSettings, 1)
    if settings is None:
        settings = HostSettings(id=1)
        session.add(settings)
        await session.commit()
    return settings


async def save_settings(session: AsyncSession, values: HostSettingsBase) -> HostSettings:
    settings = await load_settings(session)
    for key, value in values.model_dump().items():
        setattr(settings, key, value)
    if settings.servers_dir:
        settings.servers_dir = posixpath.normpath(settings.servers_dir.strip())
    session.add(settings)
    await session.commit()
    return settings


def mount_problem(servers_dir: Optional[str], mounts: Optional[list[dict]], exists: bool) -> Optional[str]:
    """Why new servers cannot be created in servers_dir, or None. `mounts` are the backend container's own
    (None when it runs natively). Compose resolves ./data against the path it sees and hands that to the host
    daemon, so inside a container the folder has to be bind-mounted at the very same path."""
    if not servers_dir:
        return "Choose the servers folder in the settings first."
    if not posixpath.isabs(servers_dir):
        return f"The servers folder must be an absolute path, not {servers_dir}."
    if mounts is not None:
        mount = next((m for m in mounts if m.get("Type") == "bind" and m.get("Source") == m.get("Destination")
                      and (servers_dir == m["Destination"] or servers_dir.startswith(m["Destination"].rstrip("/") + "/"))),
                     None)
        if mount is None:
            return (f"{servers_dir} is not mounted into the GameFleet backend at the same path. Add "
                    f"`- {servers_dir}:{servers_dir}` to the backend's volumes in docker-compose.yml.")
        if not mount.get("RW", True):
            return f"{mount['Destination']} is mounted read-only into the GameFleet backend."
    if not exists:
        return f"{servers_dir} does not exist."
    return None


async def servers_dir_problem(settings: HostSettingsBase) -> Optional[str]:
    mounts = None
    if os.path.exists("/.dockerenv"):
        try:
            mounts = (await docker_service.inspect(socket.gethostname())).get("Mounts") or []
        except (DockerUnavailable, docker.errors.DockerException, OSError) as exc:
            return f"GameFleet could not inspect its own container: {exc}"
    return mount_problem(settings.servers_dir, mounts, bool(settings.servers_dir) and os.path.isdir(settings.servers_dir))
