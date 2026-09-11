import uuid
from typing import Optional
from sqlalchemy import String
from sqlmodel import SQLModel, Field

from gamefleet_backend.models.game_server_type import GameServerType


class GameServerBase(SQLModel):
    # Stored as plain text so adding new game types never requires altering a Postgres enum type.
    game: GameServerType = Field(sa_type=String(50))
    name: str = Field(max_length=100)
    address: str = Field(max_length=100)
    port: int = Field(ge=1, le=65535)
    # Query port if it differs from the game port (defaults per game in GAME_CATALOG).
    query_port: Optional[int] = Field(default=None, ge=1, le=65535)
    # RCON access, used by games that expose no public query protocol (Factorio, private ARK: SA).
    rcon_port: Optional[int] = Field(default=None, ge=1, le=65535)


class GameServer(GameServerBase, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    rcon_password: Optional[str] = Field(default=None, max_length=200)


class GameServerPublic(GameServerBase):
    """API representation of a server: everything except secrets."""
    id: str
    has_rcon: bool = False

    @classmethod
    def from_server(cls, server: GameServer) -> "GameServerPublic":
        return cls(**server.model_dump(exclude={"rcon_password"}), has_rcon=bool(server.rcon_password))
