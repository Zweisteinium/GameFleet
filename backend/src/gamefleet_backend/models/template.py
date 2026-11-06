"""Server templates (templates/*.yaml): everything GameFleet needs to create a game server, and the API models of
the create flow. A template describes one image; its variables drive the create wizard and become the
environment of the generated compose file."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

from gamefleet_backend.models.game_server_type import GameServerType


class TemplatePort(BaseModel):
    name: str  # game, query, rcon, ...
    port: int = Field(ge=1, le=65535)  # inside the container, and the default host port
    protocol: Literal["tcp", "udp"] = "tcp"
    # False keeps the port inside Docker: RCON is only used by GameFleet and the image's own tools.
    publish: bool = True
    # Moves with the game port when the user picks another one, keeping its distance (Valheim's query port).
    follows: bool = False


class Option(BaseModel):
    value: str
    label: Optional[str] = None
    hint: Optional[str] = None


class TemplateVariable(BaseModel):
    env: str
    label: str
    # memory: heap size like 6G (also sets the container limit); secret: generated once into .env;
    # modrinth-modpack: a project slug, ID or URL, picked by searching Modrinth.
    type: Literal["text", "number", "select", "boolean", "memory", "secret", "modrinth-modpack"] = "text"
    default: Optional[str] = None
    options: list[Option] = []
    help: Optional[str] = None
    placeholder: Optional[str] = None
    required: bool = False
    # Hidden behind "Advanced" in the wizard and only written when it differs from the default.
    advanced: bool = False
    pattern: Optional[str] = None  # a value must match this regex
    suggest: Optional[Literal["minecraft-versions"]] = None
    # Only used (shown, validated, written) while another variable has one of these values.
    show_if: dict[str, list[str]] = {}
    # Offered on the server's Settings tab after creation (compose_service); False for choices that make it
    # another server, such as the modpack.
    settings: bool = True
    group: Optional[str] = None  # heading on the Settings tab


class ImageTag(BaseModel):
    tag: str
    label: str
    hint: Optional[str] = None


class Eula(BaseModel):
    env: str
    value: str = "TRUE"
    label: str
    url: str


class Template(BaseModel):
    id: str
    game: GameServerType
    label: str
    description: str
    image: str
    tags: list[ImageTag] = Field(min_length=1)  # the first is the default
    folder: str  # servers are created in <servers_dir>/<folder>/<name>/
    data_path: str  # where the image keeps its data; bound to ./data next to the compose file
    # More folders next to data/, by folder name: path in the container (e.g. Valheim's server files).
    extra_volumes: dict[str, str] = {}
    eula: Optional[Eula] = None
    ports: list[TemplatePort] = Field(min_length=1)  # the first is the game port
    # Variable that tells the server its game port. Set: another game port moves the container ports too and
    # the variable gets the new port (servers that announce their port); unset: only the host port changes.
    port_env: Optional[str] = None
    stop_grace: int = Field(default=0, ge=0, le=3600)  # seconds; the host setting applies when it is longer
    variables: list[TemplateVariable] = []
    environment: dict[str, str] = {}  # fixed values
    # Variables filled from the host settings, e.g. {"UID": "owner_uid", "TZ": "timezone"}.
    settings_env: dict[str, Literal["owner_uid", "owner_gid", "timezone"]] = {}
    memory_overhead: float = Field(default=0.25, ge=0, le=2)  # container limit = heap * (1 + overhead)
    tty: bool = False
    stdin_open: bool = False
    ready_hint: Optional[str] = None  # shown while the first start runs


# ---- create flow ------------------------------------------------------------------------------------------

class CreateRequest(BaseModel):
    template: str
    name: str = Field(min_length=1, max_length=100)  # display name
    slug: str  # folder, compose project and container name; checked by template_service.render
    values: dict[str, str] = {}  # template variables by env name
    tag: Optional[str] = None  # image tag, default: the template's first
    port: Optional[int] = Field(default=None, ge=1, le=65535)  # host port for the game port
    eula: bool = False
    is_public: bool = False
    start: bool = True
    stop_conflicting: bool = False  # stop the GameFleet servers that hold the port before the first start


class PortHolder(BaseModel):
    """Another container that publishes one of the new server's host ports."""
    container_name: str
    server_id: Optional[str] = None
    server_name: Optional[str] = None
    running: bool
    ports: list[str]


class CreatePreview(BaseModel):
    folder: str  # on the host
    project: str
    container_name: str
    compose: str  # the file as it will be written (secrets stay in .env)
    secrets: list[str]  # variables written to .env
    ports: list[str]  # published, e.g. "25565/tcp"
    holders: list[PortHolder]
    problems: list[str]  # anything that stops the creation


class CreateJob(BaseModel):
    """A creation in progress or just finished (kept in memory)."""
    id: str
    name: str
    folder: str
    phase: Literal["writing", "pulling", "creating", "starting", "waiting", "done", "failed"]
    progress: Optional[float] = None  # 0..1 while pulling
    started_at: float
    finished_at: Optional[float] = None
    error: Optional[str] = None
    warning: Optional[str] = None
    server_id: Optional[str] = None
    started: bool = False
    health: Optional[str] = None  # the container's health while waiting
    ready_hint: Optional[str] = None
    log: list[str] = []  # last lines of the container log
