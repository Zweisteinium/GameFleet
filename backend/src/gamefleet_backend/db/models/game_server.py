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
    # "manual" servers are only queried; "docker" servers run on this host and can be controlled.
    source: str = Field(default="manual", max_length=20)
    # Docker container name (stable across recreations, unlike the id) for source == "docker".
    container_name: Optional[str] = Field(default=None, max_length=200)
    # Persistent data directory and world/save directory inside the container: used for sizes today
    # and for backup/restore later.
    data_path: Optional[str] = Field(default=None, max_length=300)
    world_path: Optional[str] = Field(default=None, max_length=300)
    # Shown to visitors who are not logged in.
    is_public: bool = Field(default=False)
    # Modpack (Minecraft): detected from the container (services/modpack_service.py) or typed into the form.
    # modpack_source "manual" marks the latter, which detection never overwrites.
    modpack_name: Optional[str] = Field(default=None, max_length=200)
    modpack_version: Optional[str] = Field(default=None, max_length=100)
    modpack_url: Optional[str] = Field(default=None, max_length=500)
    modpack_icon: Optional[str] = Field(default=None, max_length=500)
    modpack_source: Optional[str] = Field(default=None, max_length=20)


class GameServer(GameServerBase, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    rcon_password: Optional[str] = Field(default=None, max_length=200)


class IgnoredContainer(SQLModel, table=True):
    """Containers the user dismissed from Docker discovery."""
    container_name: str = Field(primary_key=True, max_length=200)


# What a visitor gets instead: how to reach the game, nothing about RCON or the host it runs on.
VISITOR_VIEW = {"has_rcon": False, "rcon_port": None, "source": "manual", "container_name": None,
                "data_path": None, "world_path": None}


class GameServerPublic(GameServerBase):
    """API representation of a server: everything except secrets."""
    id: str
    has_rcon: bool = False

    @classmethod
    def from_server(cls, server: GameServer, admin: bool = True) -> "GameServerPublic":
        # Validate from attributes: table rows carry `game` as plain text and must be coerced back to the enum.
        update = {"has_rcon": bool(server.rcon_password)} if admin else VISITOR_VIEW
        return cls.model_validate(server, from_attributes=True, update=update)
