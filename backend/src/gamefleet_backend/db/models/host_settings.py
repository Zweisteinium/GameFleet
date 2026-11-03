import os
from typing import Optional

from sqlmodel import Field, SQLModel


class HostSettingsBase(SQLModel):
    """Settings of this GameFleet installation, edited on the Settings page (one row)."""
    # Host folder that new servers are created in, as <servers_dir>/<game>/<name>/. The backend container must
    # mount it at the same path, because `docker compose` hands the host daemon the paths it sees itself.
    servers_dir: Optional[str] = Field(default=os.getenv("GAMEFLEET_SERVERS_DIR") or None, max_length=300)
    # Owner of the folders GameFleet creates, and the user the game runs as where the image supports it.
    owner_uid: int = Field(default=1000, ge=0, le=65535)
    owner_gid: int = Field(default=1000, ge=0, le=65535)
    # The host name players connect to; shown in the create wizard and next to the port.
    public_address: Optional[str] = Field(default=None, max_length=200)
    # Defaults for new servers.
    default_memory_gb: int = Field(default=4, ge=1, le=256)
    cpu_limit: Optional[float] = Field(default=None, gt=0, le=256)  # cores; None = no limit
    restart_policy: str = Field(default="unless-stopped", max_length=20)
    stop_grace_seconds: int = Field(default=60, ge=10, le=3600)
    timezone: str = Field(default=os.getenv("TZ") or "UTC", max_length=60)


class HostSettings(HostSettingsBase, table=True):
    id: int = Field(default=1, primary_key=True)
