from typing import Optional, Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from gamefleet_backend.db.models.game_server import GameServer
from gamefleet_backend.models.game_server_type import GameServerType


class GameServerService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all_servers(self) -> Sequence[GameServer]:
        """Get all game servers from the database."""
        statement = select(GameServer)
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def get_server_by_id(self, server_id: str) -> Optional[GameServer]:
        """Get a specific game server by ID."""
        statement = select(GameServer).where(GameServer.id == server_id)
        result = await self.session.execute(statement)
        return result.scalars().first()

    async def get_servers_by_type(self, server_type: GameServerType) -> Sequence[GameServer]:
        """Get all game servers of a specific type."""
        statement = select(GameServer).where(GameServer.game == server_type)
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def create_server(self, server_data: dict) -> GameServer:
        """Create a new game server."""
        server = GameServer(**server_data)
        self.session.add(server)
        await self.session.commit()
        await self.session.refresh(server)
        return server

    async def update_server(self, server_id: str, server_data: dict) -> Optional[GameServer]:
        """Update an existing game server."""
        server = await self.get_server_by_id(server_id)
        if server:
            for key, value in server_data.items():
                if hasattr(server, key):
                    setattr(server, key, value)
            self.session.add(server)
            await self.session.commit()
            await self.session.refresh(server)
        return server

    async def delete_server(self, server_id: str) -> bool:
        """Delete a game server by ID."""
        server = await self.get_server_by_id(server_id)
        if server:
            await self.session.delete(server)
            await self.session.commit()
            return True
        return False