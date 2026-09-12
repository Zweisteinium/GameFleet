from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from gamefleet_backend.db.session import get_session
from gamefleet_backend.services.docker_discovery_service import DockerDiscoveryService
from gamefleet_backend.services.game_server_service import GameServerService


async def get_game_server_service(
    session: AsyncSession = Depends(get_session)
) -> GameServerService:
    """Dependency to get GameServerService instance."""
    return GameServerService(session)


async def get_docker_discovery_service(
    session: AsyncSession = Depends(get_session)
) -> DockerDiscoveryService:
    return DockerDiscoveryService(session)
