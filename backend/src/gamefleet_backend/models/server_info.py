from pydantic import BaseModel, Field
from typing import Annotated, Optional, Dict, List, Any, Literal, Union
from enum import Enum


class ServerStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class BaseServerInfo(BaseModel):
    """Base model for live server information that all game servers should provide."""
    kind: Literal["base"] = "base"

    # Basic server info
    status: ServerStatus
    latency: Optional[float] = None  # milliseconds
    version: Optional[str] = None
    server_name: Optional[str] = None  # name the server advertises itself with
    description: Optional[str] = None
    icon: Optional[str] = None  # Base64-encoded
    mods: Optional[List[Dict[str, Any]]] = None
    game_mode: Optional[str] = None
    map_name: Optional[str] = None
    password_protected: Optional[bool] = None
    anti_cheat_enabled: Optional[bool] = None

    # Player information
    players_online: Optional[int] = None
    players_max: Optional[int] = None
    player_list: Optional[List[str]] = None

    error_message: Optional[str] = None


class SteamServerInfo(BaseServerInfo):
    """Generic Steam / Source engine (A2S) server information."""
    kind: Literal["steam"] = "steam"
    game: Optional[str] = None
    app_id: Optional[int] = None
    folder: Optional[str] = None
    protocol: Optional[int] = None
    bot_count: Optional[int] = None
    server_type: Optional[str] = None  # dedicated / listen / proxy
    platform: Optional[str] = None  # linux / windows / mac
    keywords: Optional[str] = None
    rules: Optional[Dict[str, str]] = None


class MinecraftServerInfo(BaseServerInfo):
    """Minecraft-specific server information (Java and Bedrock editions)."""
    kind: Literal["minecraft"] = "minecraft"
    edition: Optional[str] = None  # java / bedrock
    protocol: Optional[int] = None
    enforces_secure_chat: Optional[bool] = None


class FactorioServerInfo(BaseServerInfo):
    """Factorio-specific server information (fetched via RCON)."""
    kind: Literal["factorio"] = "factorio"
    tags: Optional[List[str]] = None
    public: Optional[bool] = None
    require_user_verification: Optional[bool] = None
    allow_commands: Optional[str] = None
    game_time: Optional[str] = None
    evolution: Optional[Dict[str, float]] = None  # surface -> evolution factor
    seed: Optional[str] = None


class SatisfactoryServerInfo(BaseServerInfo):
    """Satisfactory-specific server information."""
    kind: Literal["satisfactory"] = "satisfactory"
    session_name: Optional[str] = None
    tech_tier: Optional[int] = None
    game_phase: Optional[str] = None
    total_game_duration: Optional[int] = None
    avg_tick_rate: Optional[float] = None
    is_paused: Optional[bool] = None


class ArkServerInfo(BaseServerInfo):
    """ARK-specific server information (Survival Evolved and Survival Ascended)."""
    kind: Literal["ark"] = "ark"
    day_time: Optional[str] = None
    official: Optional[bool] = None
    pve: Optional[bool] = None
    cluster_id: Optional[str] = None
    platform_type: Optional[str] = None


LiveServerInfo = Annotated[
    Union[BaseServerInfo, SteamServerInfo, MinecraftServerInfo, FactorioServerInfo, SatisfactoryServerInfo, ArkServerInfo],
    Field(discriminator="kind"),
]
