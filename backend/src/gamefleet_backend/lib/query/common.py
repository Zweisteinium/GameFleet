import asyncio
import socket
from typing import Type, TypeVar

from gamefleet_backend.models.server_info import BaseServerInfo, ServerStatus

T = TypeVar("T", bound=BaseServerInfo)

QUERY_TIMEOUT = 5.0


def info_from_exception(cls: Type[T], exc: BaseException) -> T:
    """Map a query exception to an OFFLINE/UNKNOWN info object with a readable message."""
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, socket.timeout)):
        return cls(status=ServerStatus.OFFLINE, error_message="Connection timed out")
    if isinstance(exc, (ConnectionRefusedError, ConnectionResetError, OSError)):
        return cls(status=ServerStatus.OFFLINE, error_message=f"Server is offline or unreachable ({exc})".strip())
    return cls(status=ServerStatus.UNKNOWN, error_message=f"{type(exc).__name__}: {exc}")
