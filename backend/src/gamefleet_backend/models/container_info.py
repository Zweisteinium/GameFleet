from typing import Optional

from pydantic import BaseModel

from gamefleet_backend.models.game_server_type import GameServerType


class PortBinding(BaseModel):
    container_port: int
    host_port: Optional[int] = None  # None when the port is exposed but not published
    protocol: str  # tcp / udp


class ContainerMount(BaseModel):
    """A persistent path of the container: this is what a future backup/restore will snapshot."""
    type: str  # volume / bind
    source: str  # volume name or host path
    destination: str  # path inside the container


class ContainerInfo(BaseModel):
    id: str
    name: str
    image: str
    state: str  # running, exited, paused, restarting, dead, created
    status: str  # human readable, e.g. "Up 3 hours"
    ports: list[PortBinding]
    mounts: list[ContainerMount]
    labels: dict[str, str]
    # Where the container comes from when compose created it; tells apart many instances of one game.
    compose_project: Optional[str] = None
    compose_dir: Optional[str] = None


class DetectedGame(BaseModel):
    """What GameFleet thinks a container is, and how it would be imported."""
    game: GameServerType
    # image: a known image; keyword: image/container name; port: exposed ports only; manual: the user chose the game
    confidence: str
    reasons: list[str]
    address: str
    port: int
    query_port: Optional[int] = None
    rcon_port: Optional[int] = None
    has_rcon_password: bool = False
    data_path: Optional[str] = None
    world_path: Optional[str] = None
    name: str


class DiscoveredContainer(BaseModel):
    container: ContainerInfo
    detected: Optional[DetectedGame] = None
    # id of the GameFleet server this container is already linked to, if any
    server_id: Optional[str] = None
    ignored: bool = False


class HostStats(BaseModel):
    """Resource usage of the container behind a server. Sampled on demand and cached for a few seconds."""
    container_name: str
    state: str
    status: str
    started_at: Optional[str] = None
    cpu_percent: Optional[float] = None  # None until two samples exist
    cpu_limit: Optional[float] = None  # number of CPUs the container may use
    memory_used: Optional[int] = None  # bytes, excluding page cache
    memory_limit: Optional[int] = None  # bytes
    data_size: Optional[int] = None  # bytes under data_path
    world_size: Optional[int] = None  # bytes under world_path
    sizes_sampled_at: Optional[float] = None
    sampled_at: float
    error: Optional[str] = None
    compose_project: Optional[str] = None
    compose_dir: Optional[str] = None


class DockerStatus(BaseModel):
    available: bool
    error: Optional[str] = None
    address: str  # address that imported containers are reached at
