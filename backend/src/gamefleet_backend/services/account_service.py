"""Stored security state of the logins (second factor, sessions, invited users), see
db/models/user_security.py."""
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from sqlmodel import delete as sql_delete, select

from gamefleet_backend.db.models.user_security import UserSecurity
from gamefleet_backend.db.session import async_session

# Every request checks its session against UserSecurity.sessions_valid_after, and an invited user's token
# against their password hash. Both are cached briefly; changes made here update the cache at once, changes
# from the command line (invite, remove-user, reset-2fa) apply within this many seconds.
CACHE_SECONDS = 10
MAX_CACHED = 1000
_cache: dict[str, tuple[int, Optional[str], float]] = {}


def _remember(row: UserSecurity) -> None:
    if len(_cache) >= MAX_CACHED:
        _cache.clear()  # tokens can name any user; keep the memory that takes bounded
    _cache[row.username] = (row.sessions_valid_after, row.password_hash, time.monotonic())


async def _cached(username: str) -> tuple[int, Optional[str]]:
    hit = _cache.get(username)
    if hit and time.monotonic() - hit[2] < CACHE_SECONDS:
        return hit[0], hit[1]
    row = await get(username)
    _remember(row)
    return row.sessions_valid_after, row.password_hash


async def valid_after(username: str) -> int:
    """Session tokens of this user issued before this moment (milliseconds) are refused."""
    return (await _cached(username))[0]


async def password_hash(username: str) -> Optional[str]:
    """The password hash of an invited user who accepted the invite; None for anyone else."""
    return (await _cached(username))[1]


async def get(username: str) -> UserSecurity:
    async with async_session() as session:
        row = await session.get(UserSecurity, username)
    return row or UserSecurity(username=username)


async def find_invite(invite_hash: str) -> Optional[UserSecurity]:
    async with async_session() as session:
        result = await session.execute(select(UserSecurity).where(UserSecurity.invite_hash == invite_hash))
    return result.scalar_one_or_none()


async def all_rows() -> list[UserSecurity]:
    async with async_session() as session:
        result = await session.execute(select(UserSecurity).order_by(UserSecurity.username))
    return list(result.scalars())


async def remove(username: str) -> bool:
    """Forget the user entirely: password, authenticator, invite. Returns whether there was a row."""
    async with async_session() as session:
        async with session.begin():
            result = await session.execute(sql_delete(UserSecurity).where(UserSecurity.username == username))
    _cache.pop(username, None)
    return result.rowcount > 0


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
