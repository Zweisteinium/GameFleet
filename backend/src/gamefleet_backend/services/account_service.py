"""Stored security state of the logins (second factor, sessions), see db/models/user_security.py."""
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlmodel import select

from gamefleet_backend.db.models.user_security import UserSecurity
from gamefleet_backend.db.session import async_session

# Every request checks its session against UserSecurity.sessions_valid_after. That value is cached briefly;
# changes made here update the cache at once, changes from the command line apply within this many seconds.
CACHE_SECONDS = 10
_valid_after: dict[str, tuple[int, float]] = {}


def _remember(row: UserSecurity) -> None:
    _valid_after[row.username] = (row.sessions_valid_after, time.monotonic())


async def valid_after(username: str) -> int:
    """Session tokens of this user issued before this moment (milliseconds) are refused."""
    cached = _valid_after.get(username)
    if cached and time.monotonic() - cached[1] < CACHE_SECONDS:
        return cached[0]
    async with async_session() as session:
        row = await session.get(UserSecurity, username)
    row = row or UserSecurity(username=username)
    _remember(row)
    return row.sessions_valid_after


async def get(username: str) -> UserSecurity:
    async with async_session() as session:
        row = await session.get(UserSecurity, username)
    return row or UserSecurity(username=username)


@asynccontextmanager
async def locked(username: str) -> AsyncIterator[UserSecurity]:
    """The user's row, locked until the block ends and then saved, so two requests with the same one-time
    code cannot both succeed."""
    async with async_session() as session:
        async with session.begin():
            result = await session.execute(
                select(UserSecurity).where(UserSecurity.username == username).with_for_update())
            row = result.scalar_one_or_none()
            if row is None:
                row = UserSecurity(username=username)
                session.add(row)
            yield row
    _remember(row)
