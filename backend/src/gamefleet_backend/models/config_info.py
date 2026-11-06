from typing import Literal, Optional, Union

from pydantic import BaseModel

SettingType = Literal["bool", "int", "str", "enum"]
SettingScalar = Union[bool, int, str, None]


class SettingSpec(BaseModel):
    """One of the important settings of a game, shown as a form field."""
    key: str
    label: str
    type: SettingType
    description: str = ""
    options: list[str] = []
    group: str = ""


class SettingValue(SettingSpec):
    value: SettingScalar = None
    # The container variable that rewrites this setting on every start (itzg images): a file edit is undone.
    env_override: Optional[str] = None
    # Why the value cannot be changed any more (the world exists), None when it can.
    locked: Optional[str] = None


class ConfigFile(BaseModel):
    path: str  # inside the container; the only paths the file endpoints accept
    label: str
    size: int


class ConfigInfo(BaseModel):
    supported: bool
    reason: Optional[str] = None
    settings_file: Optional[str] = None
    settings: list[SettingValue] = []
    files: list[ConfigFile] = []
    # The game reads its settings on start, so changes need a restart to take effect.
    restart_required_hint: bool = True
    restart_needed: bool = False


class SettingsUpdate(BaseModel):
    values: dict[str, SettingScalar]


class FileContent(BaseModel):
    path: str
    content: str
    size: int


class FileUpdate(BaseModel):
    path: str
    content: str


class FileWritten(BaseModel):
    path: str
    size: int
    restart_needed: bool = True
