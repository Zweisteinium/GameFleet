"""Login for the dashboard.

Users come from the GAMEFLEET_USERS environment variable (``name:password,name2:password2``); there is no
registration. A password may be given in plain text or as an scrypt hash produced by
``python -m gamefleet_backend.auth hash``. Successful logins get a signed, stateless bearer token
(HMAC over ``user|expiry``), so nothing about sessions is stored in the database.

Visitors without a token are in public mode: they see the servers flagged ``is_public`` and nothing that
changes or reveals the host (see ``is_admin``). If no users are configured, nobody can log in: in development
mode every endpoint is then open to everyone, in production the dashboard stays read-only. The API says so in
``/api/auth/me`` and the frontend shows a warning.
"""
import base64
import hashlib
import hmac
import logging
import os
import secrets
import sys
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from gamefleet_backend.settings import DEV

log = logging.getLogger(__name__)

TOKEN_TTL = int(os.getenv("GAMEFLEET_SESSION_HOURS", "720")) * 3600  # 30 days by default
HASH_PREFIX = "scrypt$"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{HASH_PREFIX}{_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith(HASH_PREFIX):
        try:
            salt, digest = stored[len(HASH_PREFIX):].split("$", 1)
            expected = _unb64(digest)
            actual = hashlib.scrypt(password.encode(), salt=_unb64(salt), n=2**14, r=8, p=1)
            return hmac.compare_digest(actual, expected)
        except (ValueError, TypeError):
            return False
    return hmac.compare_digest(password.encode(), stored.encode())


def _load_users() -> dict[str, str]:
    users: dict[str, str] = {}
    for entry in os.getenv("GAMEFLEET_USERS", "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        name, sep, password = entry.partition(":")
        if not sep or not name.strip() or not password:
            log.warning("Ignoring malformed GAMEFLEET_USERS entry %r (expected name:password)", name)
            continue
        users[name.strip()] = password
    return users


USERS = _load_users()
AUTH_ENABLED = bool(USERS)
# Without users nobody can log in. Only a development setup treats everyone as an admin then.
OPEN_ACCESS = not AUTH_ENABLED and DEV

_secret = os.getenv("GAMEFLEET_SECRET")
SECRET_GENERATED = not _secret
SECRET = (_secret or secrets.token_urlsafe(32)).encode()


def log_startup_state() -> None:
    """Called once by the app on startup (not at import, so the CLI below stays quiet)."""
    if OPEN_ACCESS:
        log.warning("GAMEFLEET_USERS is not set: the dashboard and API are open to anyone who can reach them")
    elif not AUTH_ENABLED:
        log.error("GAMEFLEET_USERS is not set: nobody can log in, the dashboard is read-only until users are configured")
    elif SECRET_GENERATED:
        log.warning("GAMEFLEET_SECRET is not set; logins will not survive a backend restart")
    else:
        log.info("Authentication enabled for %d user(s)", len(USERS))


_DUMMY_HASH = hash_password(secrets.token_hex(8))


@dataclass(frozen=True)
class User:
    name: str


def create_token(username: str) -> tuple[str, int]:
    expires_at = int(time.time()) + TOKEN_TTL
    payload = f"{username}|{expires_at}".encode()
    signature = hmac.new(SECRET, payload, hashlib.sha256).digest()
    return f"{_b64(payload)}.{_b64(signature)}", expires_at


def verify_token(token: str) -> Optional[User]:
    try:
        payload_b64, signature_b64 = token.split(".", 1)
        payload = _unb64(payload_b64)
        expected = hmac.new(SECRET, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(signature_b64)):
            return None
        username, expires_at = payload.decode().rsplit("|", 1)
        if int(expires_at) < time.time() or username not in USERS:
            return None
        return User(name=username)
    except (ValueError, TypeError):
        return None


DOWNLOAD_TTL = 600  # seconds a download link stays valid


def create_download_token(server_id: str, path: str) -> tuple[str, int]:
    """A link token for one backup of one server; it cannot be used for anything else and expires soon,
    unlike the session token, which must not end up in URLs and access logs."""
    expires_at = int(time.time()) + DOWNLOAD_TTL
    payload = f"dl|{server_id}|{expires_at}|{path}".encode()
    signature = hmac.new(SECRET, payload, hashlib.sha256).digest()
    return f"{_b64(payload)}.{_b64(signature)}", expires_at


def verify_download_token(token: str, server_id: str, path: str) -> bool:
    try:
        payload_b64, signature_b64 = token.split(".", 1)
        payload = _unb64(payload_b64)
        if not hmac.compare_digest(hmac.new(SECRET, payload, hashlib.sha256).digest(), _unb64(signature_b64)):
            return False
        kind, token_server, expires_at, token_path = payload.decode().split("|", 3)
        return kind == "dl" and token_server == server_id and token_path == path and int(expires_at) >= time.time()
    except (ValueError, TypeError):
        return False


# Failed logins per client address: (count, window start). Enough to slow down guessing without a database.
LOGIN_ATTEMPTS = int(os.getenv("GAMEFLEET_LOGIN_ATTEMPTS", "10"))
LOGIN_WINDOW = 600  # seconds
_failures: dict[str, tuple[int, float]] = {}


def login_blocked(client: str) -> int:
    """Seconds the client has to wait before another attempt, 0 when it may try."""
    count, since = _failures.get(client, (0, 0.0))
    if time.time() - since > LOGIN_WINDOW:
        _failures.pop(client, None)
        return 0
    return int(since + LOGIN_WINDOW - time.time()) + 1 if count >= LOGIN_ATTEMPTS else 0


def login_failed(client: str) -> None:
    count, since = _failures.get(client, (0, 0.0))
    if time.time() - since > LOGIN_WINDOW:
        count, since = 0, time.time()
    _failures[client] = (count + 1, since or time.time())
    if len(_failures) > 10000:  # a flood of addresses must not grow memory without bound
        _failures.clear()


def login_succeeded(client: str) -> None:
    _failures.pop(client, None)


def authenticate(username: str, password: str) -> Optional[User]:
    stored = USERS.get(username)
    if stored is None:
        # Burn comparable time so a missing user cannot be told apart from a wrong password.
        verify_password(password, _DUMMY_HASH)
        return None
    return User(name=username) if verify_password(password, stored) else None


_bearer = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail="Not authenticated", headers={"WWW-Authenticate": "Bearer"})


async def optional_user(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Optional[User]:
    """The logged-in user, or None for a visitor. A token that is sent but rejected is a 401, never a silent
    downgrade to public mode, so clients notice that their session ended."""
    if not AUTH_ENABLED or credentials is None:
        return None
    user = verify_token(credentials.credentials)
    if user is None:
        raise _unauthorized()
    return user


async def is_admin(user: Optional[User] = Depends(optional_user)) -> bool:
    """Whether the caller may see and change everything: any logged-in user, or everyone in a development
    setup without users."""
    return OPEN_ACCESS or user is not None


async def current_user(user: Optional[User] = Depends(optional_user)) -> Optional[User]:
    """Require a login. Returns None only for the open access of a development setup without users."""
    if user is None and not OPEN_ACCESS:
        raise _unauthorized()
    return user


async def download_user(server_id: str, path: str = Query(...), dl: Optional[str] = Query(default=None),
                        user: Optional[User] = Depends(optional_user)) -> Optional[User]:
    """`current_user` for links the browser opens itself (file downloads), which cannot carry a header: a
    download token from `create_download_token` for this very server and path is accepted instead."""
    if user is None and dl is not None and AUTH_ENABLED:
        if not verify_download_token(dl, server_id, path):
            raise _unauthorized()
        return User(name="download")
    return await current_user(user)


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "hash":
        import getpass
        password = argv[2] if len(argv) > 2 else getpass.getpass("Password: ")
        print(hash_password(password))
        return 0
    print("usage: python -m gamefleet_backend.auth hash [password]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
