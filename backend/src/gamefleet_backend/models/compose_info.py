from typing import Optional

from pydantic import BaseModel

from gamefleet_backend.models.config_info import SettingScalar, SettingSpec


class ComposeSetting(SettingSpec):
    """A setting kept in the environment of the server's compose service."""
    env: str  # the variable
    value: SettingScalar = None  # as the compose file resolves it; None when it is not set
    # Why the form cannot change it (interpolated from .env, multi-line, world exists), None when it can.
    readonly: Optional[str] = None
    # The value the game currently has in its settings file, for variables that mirror one (shown when unset).
    file_value: SettingScalar = None
    multiline: bool = False  # edited as a text area (MOTD)
    motd: bool = False  # a Minecraft MOTD: shown rendered below the field


class ComposeInfo(BaseModel):
    supported: bool
    reason: Optional[str] = None
    file: Optional[str] = None  # the compose file on the host
    project: Optional[str] = None
    service: Optional[str] = None
    settings: list[ComposeSetting] = []
    # Variables whose value in the file differs from the running container: they apply on recreate.
    pending: list[str] = []


class ComposeUpdate(BaseModel):
    # By variable; None removes the variable (the image default applies again).
    values: dict[str, SettingScalar]


class ComposeFile(BaseModel):
    path: str
    content: str


class ComposeFileUpdate(BaseModel):
    content: str
