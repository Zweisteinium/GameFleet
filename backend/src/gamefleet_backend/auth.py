"""Login for the dashboard: password plus a one-time code from an authenticator app.

Users come from the GAMEFLEET_USERS environment variable (``name:password,name2:password2``) or are invited
from the command line; there is no registration. A password in GAMEFLEET_USERS may be given in plain text or
as an scrypt hash produced by ``python -m gamefleet_backend.auth hash``.

An invite (``python -m gamefleet_backend.auth invite <user>``) is a one-time link, valid for INVITE_HOURS. Its
holder chooses the password and sets up the authenticator in one go; both take effect only when the first code
is confirmed. Invited users live in the database (db/models/user_security.py), so adding or removing one needs
no restart. Inviting an existing invited user again lets them choose a new password and authenticator.

Signing in takes two steps. The password gives a short-lived challenge; the code from the authenticator turns
it into a session token. A user without an authenticator sets one up in that second step (QR code, then a
code to confirm it) and gets ten single-use recovery codes. There is no way around the second factor: a lost
authenticator is reset on the host with ``python -m gamefleet_backend.auth reset-2fa <user>``.

Tokens are stateless HMACs, signed with a key derived from GAMEFLEET_SECRET, the user name and the user's
password entry, so changing a password ends that user's sessions. "Sign out everywhere" stores a moment
before which session tokens are refused (db/models/user_security.py).

Visitors without a token are in public mode: they see the servers flagged ``is_public`` and nothing that
changes or reveals the host (see ``is_admin``). If no users are configured, nobody can log in: in development
mode every endpoint is then open to everyone, in production the dashboard stays read-only. The API says so in
``/api/auth/me`` and the frontend shows a warning.
"""
import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import sys
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from gamefleet_backend import totp
from gamefleet_backend.db.models.user_security import UserSecurity
from gamefleet_backend.services import account_service
from gamefleet_backend.settings import DEV

log = logging.getLogger(__name__)

SESSION_HOURS = int(os.getenv("GAMEFLEET_SESSION_HOURS", "24"))
TOKEN_TTL = SESSION_HOURS * 3600
CHALLENGE_TTL = 300  # seconds between the password and the code
ENROLL_TTL = 600  # seconds to scan the QR code and confirm it
INVITE_HOURS = 24
PASSWORD_MIN_LENGTH = 10  # for passwords chosen on the invite page
# Names of invited users; GAMEFLEET_USERS is looser for compatibility.
INVITE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,31}")
# Address of the dashboard, only used to print complete invite links.
PUBLIC_URL = os.getenv("GAMEFLEET_URL", "").strip().rstrip("/")
HASH_PREFIX = "scrypt$"

# Token kinds; the kind is part of the signed text and of the key, so one kind never passes for another.
# INVITE is the enrollment challenge of the invite page.
SESSION, CHALLENGE, ENROLL, INVITE = "s", "mfa", "enroll", "invite"


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
        name = name.strip()
        if not sep or not name or not password:
            log.warning("Ignoring malformed GAMEFLEET_USERS entry %r (expected name:password)", name)
            continue
        if "|" in name or len(name) > 100:
            log.warning("Ignoring GAMEFLEET_USERS entry %r: names must not contain | or exceed 100 characters", name)
            continue
        users[name] = password
    return users


USERS = _load_users()
AUTH_ENABLED = bool(USERS)
# Without users nobody can log in. Only a development setup treats everyone as an admin then.
OPEN_ACCESS = not AUTH_ENABLED and DEV
PLAIN_PASSWORDS = sorted(name for name, stored in USERS.items() if not stored.startswith(HASH_PREFIX))
# Plain-text passwords are checked against a hash made at startup, so every check costs the same scrypt time
# and a wrong user name cannot be told apart from a wrong password.
_CHECK = {name: stored if stored.startswith(HASH_PREFIX) else hash_password(stored) for name, stored in USERS.items()}

_secret = os.getenv("GAMEFLEET_SECRET")
SECRET_GENERATED = not _secret
SECRET = (_secret or secrets.token_urlsafe(32)).encode()


class ConfigurationError(RuntimeError):
    pass


def log_startup_state() -> None:
    """Called once by the app on startup (not at import, so the CLI below stays quiet)."""
    if OPEN_ACCESS:
        log.warning("GAMEFLEET_USERS is not set: the dashboard and API are open to anyone who can reach them")
    elif not AUTH_ENABLED:
        log.error("GAMEFLEET_USERS is not set: nobody can log in, the dashboard is read-only until users are configured")
    else:
        if SECRET_GENERATED:
            # The secret also derives the authenticator keys: a new one on every start would lock everyone out.
            if not DEV:
                raise ConfigurationError("GAMEFLEET_SECRET must be set when GAMEFLEET_USERS is: it signs logins and "
                                         "derives the two-factor keys (generate one with: openssl rand -hex 32)")
            log.warning("GAMEFLEET_SECRET is not set; logins and authenticators will not survive a restart")
        elif len(SECRET) < 32:
            log.warning("GAMEFLEET_SECRET is short; use at least 32 random characters (openssl rand -hex 32)")
        if PLAIN_PASSWORDS:
            log.warning("Plain-text password in GAMEFLEET_USERS for %s; store an scrypt hash instead (make hash)",
                        ", ".join(PLAIN_PASSWORDS))
        log.info("Authentication with two factors enabled for %d user(s)", len(USERS))


_DUMMY_HASH = hash_password(secrets.token_hex(8))


@dataclass(frozen=True)
class User:
    name: str


# ---- keys and tokens -------------------------------------------------------------------------------------

def _key(*parts: str) -> bytes:
    return hmac.new(SECRET, "|".join(parts).encode(), hashlib.sha256).digest()


async def password_entry(username: str) -> Optional[str]:
    """The user's entry in GAMEFLEET_USERS, else an invited user's password hash; None for nobody."""
    if username in USERS:
        return USERS[username]
    return await account_service.password_hash(username)


async def _binding(kind: str, username: str) -> Optional[str]:
    """What a token of this kind is bound to; when it changes, the token stops working. Invite tokens are
    bound to the open invite (using or replacing it ends them), all others to the user's password."""
    if kind == INVITE:
        row = await account_service.get(username)
        return row.invite_hash if row.invite_hash and row.invite_expires > time.time() else None
    return await password_entry(username)


def _user_key(kind: str, username: str, binding: str) -> bytes:
    return _key("token", kind, username, binding)


def totp_key(username: str, nonce: str) -> bytes:
    """The authenticator key of a user: derived, never stored (see UserSecurity.totp_nonce)."""
    return _key("totp", username, nonce)[:20]


def recovery_hash(username: str, code: str) -> str:
    return hmac.new(_key("recovery", username), totp.normalize_recovery(code).encode(), hashlib.sha256).hexdigest()


def now_ms() -> int:
    return time.time_ns() // 1_000_000


async def _sign(kind: str, username: str, fields: list[str], ttl: int) -> tuple[str, int]:
    binding = await _binding(kind, username)
    if binding is None:
        raise ValueError(f"No user {username!r} to sign a token for")
    expires_at = int(time.time()) + ttl
    payload = "|".join([kind, username, *fields, str(expires_at)]).encode()
    signature = hmac.new(_user_key(kind, username, binding), payload, hashlib.sha256).digest()
    return f"{_b64(payload)}.{_b64(signature)}", expires_at


async def _open(token: str, *kinds: str) -> Optional[tuple[str, str, list[str]]]:
    """(kind, user name, fields) of a valid, unexpired token of one of these kinds; None for anything else."""
    try:
        payload_b64, signature_b64 = token.split(".", 1)
        payload, signature = _unb64(payload_b64), _unb64(signature_b64)
        parts = payload.decode().split("|")
        if len(parts) < 3 or parts[0] not in kinds or int(parts[-1]) < time.time():
            return None
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    kind, username = parts[0], parts[1]
    binding = await _binding(kind, username)
    if binding is None:
        return None
    expected = hmac.new(_user_key(kind, username, binding), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, signature):
        return None
    return kind, username, parts[2:-1]


async def create_token(username: str) -> tuple[str, int]:
    """A session token. It carries the moment it was issued, which "sign out everywhere" compares against."""
    return await _sign(SESSION, username, [str(now_ms())], TOKEN_TTL)


async def verify_token(token: str) -> Optional[User]:
    opened = await _open(token, SESSION)
    if opened is None:
        return None
    _, username, fields = opened
    try:
        issued = int(fields[0])
    except (IndexError, ValueError):
        return None
    if issued < await account_service.valid_after(username):
        return None
    return User(name=username)


async def create_challenge(username: str) -> tuple[str, int]:
    """Proof that the password was right, valid for a few minutes, to be completed with a code."""
    return await _sign(CHALLENGE, username, [], CHALLENGE_TTL)


async def create_enrollment(username: str, kind: str = ENROLL) -> tuple[str, int, str]:
    """A challenge for setting up an authenticator: (token, expiry, nonce of the new key). ENROLL after the
    password of a user without one, INVITE on the invite page."""
    nonce = secrets.token_hex(16)
    token, expires_at = await _sign(kind, username, [nonce], ENROLL_TTL)
    return token, expires_at, nonce


async def open_challenge(token: str) -> Optional[tuple[str, str, Optional[str]]]:
    """(kind, user name, nonce for an enrollment) of a valid challenge token."""
    opened = await _open(token, CHALLENGE, ENROLL, INVITE)
    if opened is None:
        return None
    kind, username, fields = opened
    if kind == CHALLENGE:
        return (kind, username, None) if not fields else None
    return (kind, username, fields[0]) if len(fields) == 1 else None


DOWNLOAD_TTL = 600  # seconds a download link stays valid


def create_download_token(server_id: str, path: str) -> tuple[str, int]:
    """A link token for one backup of one server; it cannot be used for anything else and expires soon,
    unlike the session token, which must not end up in URLs and access logs."""
    expires_at = int(time.time()) + DOWNLOAD_TTL
    payload = f"dl|{server_id}|{expires_at}|{path}".encode()
    signature = hmac.new(_key("download"), payload, hashlib.sha256).digest()
    return f"{_b64(payload)}.{_b64(signature)}", expires_at


def verify_download_token(token: str, server_id: str, path: str) -> bool:
    try:
        payload_b64, signature_b64 = token.split(".", 1)
        payload = _unb64(payload_b64)
        if not hmac.compare_digest(hmac.new(_key("download"), payload, hashlib.sha256).digest(), _unb64(signature_b64)):
            return False
        kind, token_server, expires_at, token_path = payload.decode().split("|", 3)
        return kind == "dl" and token_server == server_id and token_path == path and int(expires_at) >= time.time()
    except (ValueError, TypeError, UnicodeDecodeError):
        return False


# ---- second factor ---------------------------------------------------------------------------------------

class AlreadyEnrolled(Exception):
    """An enrollment challenge for a user who has set up an authenticator in the meantime."""


def _new_recovery_codes(username: str) -> tuple[list[str], str]:
    codes = [totp.recovery_code() for _ in range(totp.RECOVERY_COUNT)]
    return codes, json.dumps([recovery_hash(username, c) for c in codes])


async def check_second_factor(username: str, code: str, allow_recovery: bool = True) -> bool:
    """Accept a current authenticator code (once) or an unused recovery code (which is used up)."""
    text = code.strip().replace(" ", "")
    async with account_service.locked(username) as row:
        if not row.totp_nonce:
            return False
        if totp.is_code(text):
            step = totp.match(totp_key(username, row.totp_nonce), text, row.totp_last_step)
            if step is None:
                return False
            row.totp_last_step = step
            return True
        if not allow_recovery:
            return False
        stored = json.loads(row.recovery_codes or "[]")
        digest = recovery_hash(username, text)
        if digest not in stored:
            return False
        stored.remove(digest)
        row.recovery_codes = json.dumps(stored)
        log.warning("User %r signed in with a recovery code; %d left", username, len(stored))
        return True


async def enroll(username: str, nonce: str, code: str) -> Optional[list[str]]:
    """Store the authenticator after its first code; returns the recovery codes, None for a wrong code.
    Ends every earlier session of the user, which were all made without a second factor."""
    async with account_service.locked(username) as row:
        if row.totp_nonce:
            raise AlreadyEnrolled()
        step = totp.match(totp_key(username, nonce), code, 0)
        if step is None:
            return None
        codes, hashes = _new_recovery_codes(username)
        row.totp_nonce, row.totp_last_step, row.recovery_codes = nonce, step, hashes
        row.sessions_valid_after = now_ms()
    log.info("User %r set up an authenticator", username)
    return codes


async def renew_recovery_codes(username: str, code: str) -> Optional[list[str]]:
    """Replace the recovery codes; needs a current authenticator code (a recovery code is not enough)."""
    if not await check_second_factor(username, code, allow_recovery=False):
        return None
    codes, hashes = _new_recovery_codes(username)
    async with account_service.locked(username) as row:
        row.recovery_codes = hashes
    return codes


async def security_state(username: str) -> tuple[bool, int]:
    """(authenticator set up, unused recovery codes)."""
    row = await account_service.get(username)
    return row.totp_nonce is not None, len(json.loads(row.recovery_codes or "[]"))


async def sign_out_everywhere(username: str) -> None:
    async with account_service.locked(username) as row:
        row.sessions_valid_after = now_ms()
    log.info("User %r ended all sessions", username)


# ---- invites ---------------------------------------------------------------------------------------------

class InviteError(Exception):
    """An invite that cannot be created or used, or a password the invite page does not accept. The message
    is meant for the person in front of it."""


def _invite_hash(token: str) -> str:
    return hmac.new(_key("invite"), token.encode(), hashlib.sha256).hexdigest()


def invite_link(token: str) -> str:
    # The token goes after '#': browsers do not send that part, so it stays out of proxy and access logs.
    return f"{PUBLIC_URL}/invite#{token}"


async def create_invite(username: str) -> tuple[str, int]:
    """A one-time invite for a new user, or a fresh password and authenticator for an invited one:
    (token for the link, expiry). Replaces any open invite of that user."""
    if not INVITE_NAME.fullmatch(username):
        raise InviteError("Names are 1-32 letters, digits, '.', '_' or '-', starting with a letter or digit")
    if username in USERS:
        raise InviteError(f"{username!r} is configured in GAMEFLEET_USERS; change the password there")
    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + INVITE_HOURS * 3600
    async with account_service.locked(username) as row:
        row.invite_hash, row.invite_expires, row.invite_password = _invite_hash(token), expires_at, None
    log.info("Invite for user %r created, valid for %d h", username, INVITE_HOURS)
    return token, expires_at


async def open_invite(token: str) -> Optional[tuple[str, int]]:
    """(user name, expiry) of an open invite; None for an unknown, used or expired one."""
    if not token or len(token) > 200:
        return None
    row = await account_service.find_invite(_invite_hash(token))
    if row is None or row.invite_expires <= time.time():
        return None
    return row.username, row.invite_expires


def password_problem(username: str, password: str) -> Optional[str]:
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"Use at least {PASSWORD_MIN_LENGTH} characters."
    if password.strip().lower() == username.lower():
        return "The password must not be the user name."
    return None


async def accept_invite(token: str, password: str) -> Optional[tuple[str, str, int, str]]:
    """First step on the invite page: keep the chosen password (it takes effect with the authenticator) and
    return (user name, INVITE challenge, its expiry, nonce of the new key). None for an unusable invite;
    InviteError for a password that is not accepted."""
    opened = await open_invite(token)
    if opened is None:
        return None
    username, _ = opened
    if problem := password_problem(username, password):
        raise InviteError(problem)
    hashed = await asyncio.to_thread(hash_password, password)
    digest = _invite_hash(token)
    async with account_service.locked(username) as row:
        if row.invite_hash != digest or row.invite_expires <= time.time():
            return None
        row.invite_password = hashed
    challenge, expires_at, nonce = await create_enrollment(username, INVITE)
    return username, challenge, expires_at, nonce


async def finish_invite(username: str, nonce: str, code: str) -> Optional[list[str]]:
    """Last step on the invite page: the first code of the new authenticator. Sets the password and the
    authenticator, closes the invite and ends earlier sessions of the user. Returns the recovery codes, None
    for a wrong code; InviteError when the invite was used, replaced or has expired meanwhile."""
    async with account_service.locked(username) as row:
        if not row.invite_hash or row.invite_expires <= time.time() or not row.invite_password:
            raise InviteError("This invite has expired or was already used.")
        step = totp.match(totp_key(username, nonce), code.strip().replace(" ", ""), 0)
        if step is None:
            return None
        codes, hashes = _new_recovery_codes(username)
        row.password_hash, row.invite_password = row.invite_password, None
        row.invite_hash, row.invite_expires = None, 0
        row.totp_nonce, row.totp_last_step, row.recovery_codes = nonce, step, hashes
        row.sessions_valid_after = now_ms()
    log.info("User %r accepted the invite and set up an authenticator", username)
    return codes


# ---- brute-force limits ----------------------------------------------------------------------------------

# Failed logins per client address: (count, window start). Enough to slow down guessing without a database.
LOGIN_ATTEMPTS = int(os.getenv("GAMEFLEET_LOGIN_ATTEMPTS", "10"))
LOGIN_WINDOW = 600  # seconds
MAX_TRACKED = 10000
_failures: dict[str, tuple[int, float]] = {}


def _prune(table: dict, expired) -> None:
    """Bound the memory a flood of addresses can take: drop expired entries, then the oldest."""
    if len(table) <= MAX_TRACKED:
        return
    for key in [k for k, v in table.items() if expired(v)]:
        del table[key]
    while len(table) > MAX_TRACKED:
        del table[next(iter(table))]


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
    _prune(_failures, lambda v: time.time() - v[1] > LOGIN_WINDOW)


def login_succeeded(client: str) -> None:
    _failures.pop(client, None)


# Wrong codes per user, after the password was right: (failures, locked until, lockouts so far). Each lockout
# doubles the next one, so someone who has the password cannot keep guessing codes at a steady rate.
FACTOR_ATTEMPTS = 5
FACTOR_LOCK = 900  # seconds, for the first lockout
FACTOR_LOCK_MAX = 86400
_factor_failures: dict[str, tuple[int, float, int]] = {}


def factor_blocked(username: str) -> int:
    _, until, _ = _factor_failures.get(username, (0, 0.0, 0))
    return max(0, int(until - time.time()) + 1) if until > time.time() else 0


def factor_failed(username: str) -> None:
    failures, until, lockouts = _factor_failures.get(username, (0, 0.0, 0))
    failures += 1
    log.warning("Wrong second factor for user %r (the password was right)", username)
    if failures >= FACTOR_ATTEMPTS:
        lockouts += 1
        until = time.time() + min(FACTOR_LOCK * 2 ** (lockouts - 1), FACTOR_LOCK_MAX)
        failures = 0
        log.warning("Second factor of user %r locked for %d s after repeated wrong codes",
                    username, int(until - time.time()))
    _factor_failures[username] = (failures, until, lockouts)


def factor_succeeded(username: str) -> None:
    _factor_failures.pop(username, None)


# The frontend forwards the browser's address in this header. It is believed only from the frontend
# container (GAMEFLEET_FRONTEND_HOST, resolved through Docker's DNS); everyone else is limited by their own
# address, so the header cannot be used to dodge the limit.
CLIENT_HEADER = "x-gamefleet-client"
FRONTEND_HOSTS = [h.strip() for h in os.getenv("GAMEFLEET_FRONTEND_HOST", "frontend").split(",") if h.strip()]
_frontend: tuple[frozenset[str], float] = (frozenset(), 0.0)


async def _frontend_addresses() -> frozenset[str]:
    global _frontend
    addresses, resolved_at = _frontend
    if time.monotonic() - resolved_at < 60:
        return addresses
    found: set[str] = set()
    loop = asyncio.get_running_loop()
    for host in FRONTEND_HOSTS:
        try:
            found.update(info[4][0] for info in await loop.getaddrinfo(host, None))
        except OSError:
            pass
    _frontend = (frozenset(found), time.monotonic())
    return _frontend[0]


async def client_address(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    claimed = request.headers.get(CLIENT_HEADER)
    if claimed and peer in await _frontend_addresses():
        try:
            return str(ipaddress.ip_address(claimed.strip()))
        except ValueError:
            pass
    return peer


def limit_key(address: str) -> str:
    """IPv6 clients usually own a whole /64, so they are limited as one."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return address
    if ip.version == 4:
        return str(ip)
    if ip.ipv4_mapped is not None:
        return str(ip.ipv4_mapped)
    return str(ipaddress.ip_network(f"{ip}/64", strict=False))


async def authenticate(username: str, password: str) -> Optional[User]:
    """Check a password; the scrypt work runs in a thread so it does not block other requests."""
    stored = _CHECK.get(username)
    if stored is None and username and "|" not in username and len(username) <= 100:
        stored = await account_service.password_hash(username)
    if stored is None:
        # Burn comparable time so a missing user cannot be told apart from a wrong password.
        await asyncio.to_thread(verify_password, password, _DUMMY_HASH)
        return None
    return User(name=username) if await asyncio.to_thread(verify_password, password, stored) else None


# ---- FastAPI dependencies --------------------------------------------------------------------------------

_bearer = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail="Not authenticated", headers={"WWW-Authenticate": "Bearer"})


async def optional_user(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Optional[User]:
    """The logged-in user, or None for a visitor. A token that is sent but rejected is a 401, never a silent
    downgrade to public mode, so clients notice that their session ended."""
    if not AUTH_ENABLED or credentials is None:
        return None
    user = await verify_token(credentials.credentials)
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


# ---- command line ----------------------------------------------------------------------------------------

USAGE = """usage:
  python -m gamefleet_backend.auth invite <user>       one-time link (valid {hours} h) with which a new user chooses
                                                     a password and sets up an authenticator; for an invited
                                                     user it replaces both
  python -m gamefleet_backend.auth users               all users with their authenticator and invite state
  python -m gamefleet_backend.auth remove-user <user>  delete an invited user; their sessions end
  python -m gamefleet_backend.auth reset-2fa <user>    forget the user's authenticator and end their sessions;
                                                     the next login sets up a new one
  python -m gamefleet_backend.auth hash [password]     scrypt hash for GAMEFLEET_USERS""".format(hours=INVITE_HOURS)


def _when(seconds: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M %Z", time.localtime(seconds))


async def _cli_invite(username: str) -> int:
    if not AUTH_ENABLED or SECRET_GENERATED:
        print("Set GAMEFLEET_USERS and GAMEFLEET_SECRET first; invited users sign in next to those users.",
              file=sys.stderr)
        return 1
    try:
        token, expires_at = await create_invite(username)
    except InviteError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Invite for {username!r}, valid until {_when(expires_at)}:\n\n  {invite_link(token)}\n")
    if not PUBLIC_URL:
        print("Put the dashboard's address in front (set GAMEFLEET_URL to print the whole link).")
    print("Whoever opens it chooses the password and sets up the authenticator, so send it only to them.\n"
          "It works once; a new invite for the same name replaces it.")
    return 0


async def _cli_users() -> int:
    rows = {row.username: row for row in await account_service.all_rows()}
    names = list(USERS) + [n for n, r in rows.items() if n not in USERS and (r.password_hash or r.invite_hash)]
    if not names:
        print("No users.")
        return 0
    lines = [("NAME", "FROM", "AUTHENTICATOR", "STATE")]
    for name in names:
        row = rows.get(name) or UserSecurity(username=name)
        if name in USERS:
            source, state = "GAMEFLEET_USERS", "active"
        else:
            source = "invite"
            state = "active" if row.password_hash else "not accepted yet"
            if row.invite_hash:
                open_now = row.invite_expires > time.time()
                note = f"invite open until {_when(row.invite_expires)}" if open_now else "invite expired"
                state = f"{state}, {note}" if row.password_hash else note
        lines.append((name, source, "set up" if row.totp_nonce else "-", state))
    widths = [max(len(line[i]) for line in lines) for i in range(3)]
    for line in lines:
        print("  ".join(cell.ljust(width) for cell, width in zip(line, widths)) + "  " + line[3])
    return 0


async def _cli_remove(username: str) -> int:
    if username in USERS:
        print(f"{username!r} is configured in GAMEFLEET_USERS; remove it there.", file=sys.stderr)
        return 1
    if not await account_service.remove(username):
        print(f"No invited user {username!r}.", file=sys.stderr)
        return 1
    print(f"User {username!r} removed; their sessions end within {account_service.CACHE_SECONDS} seconds.")
    return 0


async def _cli_reset_2fa(username: str) -> int:
    if username not in USERS and not (await account_service.get(username)).password_hash:
        print(f"No user {username!r}.", file=sys.stderr)
        return 1
    async with account_service.locked(username) as row:
        row.totp_nonce, row.totp_last_step, row.recovery_codes = None, 0, "[]"
        row.sessions_valid_after = now_ms()
    print(f"Authenticator of {username!r} removed and sessions ended; the next login sets up a new one.")
    return 0


def main(argv: list[str]) -> int:
    command, args = (argv[1], argv[2:]) if len(argv) > 1 else ("", [])
    if command == "hash" and len(args) <= 1:
        import getpass
        print(hash_password(args[0] if args else getpass.getpass("Password: ")))
        return 0
    if command == "invite" and len(args) == 1:
        return asyncio.run(_cli_invite(args[0]))
    if command == "users" and not args:
        return asyncio.run(_cli_users())
    if command == "remove-user" and len(args) == 1:
        return asyncio.run(_cli_remove(args[0]))
    if command == "reset-2fa" and len(args) == 1:
        return asyncio.run(_cli_reset_2fa(args[0]))
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
