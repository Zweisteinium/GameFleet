from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from gamefleet_backend import auth, totp
from gamefleet_backend.settings import DEV

router = APIRouter()


class LoginRequest(BaseModel):
    username: str = Field(max_length=200)
    password: str = Field(max_length=1000)


class SecondFactorRequest(BaseModel):
    # The challenge from `login`.
    challenge: str = Field(max_length=2000)
    # Six digits from the authenticator, or a recovery code.
    code: str = Field(max_length=40)


class LoginResult(BaseModel):
    """`totp`: send a code with the challenge to `loginSecondFactor`. `enroll`: no authenticator yet; show
    `totp_uri` as a QR code (or `totp_secret` to type in) and send its first code with the challenge.
    `ok`: signed in with `token`; after an enrollment `recovery_codes` holds the codes, shown only this once."""
    status: Literal["ok", "totp", "enroll"]
    username: str
    token: Optional[str] = None
    expires_at: Optional[int] = None  # unix seconds, of the token or the challenge
    challenge: Optional[str] = None
    totp_secret: Optional[str] = None
    totp_uri: Optional[str] = None
    recovery_codes: Optional[list[str]] = None


class SessionInfo(BaseModel):
    auth_enabled: bool
    username: str | None = None
    # False for a visitor in public mode; true when logged in, or for everyone in a dev setup without users.
    admin: bool
    # Development mode (GAMEFLEET_DEV=true): API docs are served; the dashboard shows a banner.
    dev: bool


class SecurityInfo(BaseModel):
    totp_enabled: bool
    recovery_codes_left: int
    session_hours: int


class CodeRequest(BaseModel):
    code: str = Field(max_length=40)


class RecoveryCodes(BaseModel):
    recovery_codes: list[str]


def _too_many(wait: int, what: str) -> HTTPException:
    return HTTPException(status_code=429, detail=f"Too many {what}; try again in {max(1, round(wait / 60))} min.",
                         headers={"Retry-After": str(wait)})


async def _client(request: Request) -> str:
    return auth.limit_key(await auth.client_address(request))


@router.post("/login", response_model=LoginResult, operation_id="login")
async def login(body: LoginRequest, request: Request):
    """First step: the password. Answers with a challenge for the second factor, never with a session.
    Ten failures from one address (an IPv6 /64) block it for ten minutes (429 with Retry-After)."""
    if not auth.AUTH_ENABLED:
        raise HTTPException(status_code=400, detail="No users are configured (GAMEFLEET_USERS is not set)")
    client = await _client(request)
    if wait := auth.login_blocked(client):
        raise _too_many(wait, "failed sign-ins")
    username = body.username.strip()
    user = await run_in_threadpool(auth.authenticate, username, body.password)
    if user is None:
        auth.login_failed(client)
        auth.log.warning("Failed login for user %r from %s", username, client)
        raise HTTPException(status_code=401, detail="Wrong username or password")
    enabled, _ = await auth.security_state(user.name)
    if enabled:
        challenge, expires_at = auth.create_challenge(user.name)
        return LoginResult(status="totp", username=user.name, challenge=challenge, expires_at=expires_at)
    challenge, expires_at, nonce = auth.create_enrollment(user.name)
    key = auth.totp_key(user.name, nonce)
    return LoginResult(status="enroll", username=user.name, challenge=challenge, expires_at=expires_at,
                       totp_secret=totp.secret_text(key), totp_uri=totp.uri(key, user.name))


@router.post("/login/totp", response_model=LoginResult, operation_id="loginSecondFactor")
async def login_second_factor(body: SecondFactorRequest, request: Request):
    """Second step: a code from the authenticator (or a recovery code) for the challenge from `login`.
    Five wrong codes lock the user's second step for 15 minutes, doubling with every further lockout."""
    client = await _client(request)
    if wait := auth.login_blocked(client):
        raise _too_many(wait, "failed sign-ins")
    opened = auth.open_challenge(body.challenge)
    if opened is None:
        raise HTTPException(status_code=401, detail="The sign-in has expired; enter your password again.")
    kind, username, nonce = opened
    if wait := auth.factor_blocked(username):
        raise _too_many(wait, "wrong codes")
    codes = None
    try:
        if kind == auth.ENROLL:
            codes = await auth.enroll(username, nonce, body.code)
            ok = codes is not None
        else:
            ok = await auth.check_second_factor(username, body.code)
    except auth.AlreadyEnrolled:
        raise HTTPException(status_code=409, detail="An authenticator is already set up; sign in again.")
    if not ok:
        auth.login_failed(client)
        auth.factor_failed(username)
        raise HTTPException(status_code=401, detail="Wrong code")
    auth.login_succeeded(client)
    auth.factor_succeeded(username)
    token, expires_at = auth.create_token(username)
    return LoginResult(status="ok", username=username, token=token, expires_at=expires_at, recovery_codes=codes)


@router.get("/me", response_model=SessionInfo, operation_id="getSession")
async def me(user: auth.User | None = Depends(auth.optional_user)):
    """Who the caller is: a visitor, a logged-in user, or anyone with login disabled. 401 for a rejected token."""
    return SessionInfo(
        auth_enabled=auth.AUTH_ENABLED,
        username=user.name if user else None,
        admin=auth.OPEN_ACCESS or user is not None,
        dev=DEV,
    )


def _signed_in(user: auth.User | None) -> auth.User:
    if user is None:  # development setup without users: there is no account to manage
        raise HTTPException(status_code=400, detail="No users are configured (GAMEFLEET_USERS is not set)")
    return user


@router.get("/security", response_model=SecurityInfo, operation_id="getSecurity")
async def security(user: auth.User | None = Depends(auth.current_user)):
    """Second factor and session length of the signed-in user."""
    enabled, left = await auth.security_state(_signed_in(user).name)
    return SecurityInfo(totp_enabled=enabled, recovery_codes_left=left, session_hours=auth.SESSION_HOURS)


@router.post("/recovery-codes", response_model=RecoveryCodes, operation_id="renewRecoveryCodes")
async def renew_recovery_codes(body: CodeRequest, user: auth.User | None = Depends(auth.current_user)):
    """Replace all recovery codes. Needs a current code from the authenticator."""
    name = _signed_in(user).name
    if wait := auth.factor_blocked(name):
        raise _too_many(wait, "wrong codes")
    codes = await auth.renew_recovery_codes(name, body.code)
    if codes is None:
        auth.factor_failed(name)
        raise HTTPException(status_code=400, detail="Wrong code")
    auth.factor_succeeded(name)
    return RecoveryCodes(recovery_codes=codes)


@router.post("/logout-all", status_code=204, operation_id="logoutEverywhere")
async def logout_everywhere(user: auth.User | None = Depends(auth.current_user)):
    """End every session of the signed-in user, this one included."""
    await auth.sign_out_everywhere(_signed_in(user).name)
