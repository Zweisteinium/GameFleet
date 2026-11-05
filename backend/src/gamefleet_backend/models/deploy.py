from typing import Literal, Optional, Union

from pydantic import BaseModel, Field

from gamefleet_backend.models.game_server_type import GameServerType

FieldValue = Union[bool, int, str, None]


class DeployField(BaseModel):
    """One environment variable of a template, shown as a form field."""
    key: str
    label: str
    type: Literal["bool", "int", "str", "enum", "secret"]
    default: FieldValue = None
    required: bool = False
    options: list[str] = []
    description: str = ""
    group: str = ""


class DeployPort(BaseModel):
    label: str  # "game", "rcon", "query"...
    container_port: int
    protocol: Literal["tcp", "udp"]
    default_host_port: Optional[int] = None  # None: not published unless the user asks


class DeployTemplate(BaseModel):
    id: str  # the game value
    game: GameServerType
    label: str
    image: str
    description: str
    memory_hint: str
    fields: list[DeployField]
    ports: list[DeployPort]
    data_dir: str  # inside the container
    stop_timeout: int


class DeployCheck(BaseModel):
    template: str
    name: str
    host_ports: dict[str, int] = {}


class PortIssue(BaseModel):
    label: str
    port: int
    protocol: str
    container: str
    state: str  # running: a conflict; anything else: a warning (the port is taken while that container runs)


class DeployCheckResult(BaseModel):
    slug: str
    name_free: bool
    directory: str
    conflicts: list[PortIssue] = []
    warnings: list[PortIssue] = []


class DeployRequest(BaseModel):
    template: str
    name: str = Field(min_length=1, max_length=100)
    host_ports: dict[str, int] = {}
    values: dict[str, FieldValue] = {}
    is_public: bool = False
    start: bool = True


class DeployJob(BaseModel):
    id: str
    template: str
    name: str
    container_name: str
    directory: str
    phase: Literal["queued", "pulling", "creating", "starting", "importing", "done", "failed"] = "queued"
    progress: Optional[float] = None  # 0-1 while pulling
    detail: Optional[str] = None
    error: Optional[str] = None
    server_id: Optional[str] = None
    started_at: float
    finished_at: Optional[float] = None
