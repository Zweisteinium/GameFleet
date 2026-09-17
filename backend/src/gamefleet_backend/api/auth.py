from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gamefleet_backend import auth
from gamefleet_backend.settings import DEV

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    expires_at: int  # unix seconds


class SessionInfo(BaseModel):
    auth_enabled: bool
    username: str | None = None
    # False for a visitor in public mode; true when logged in, or for everyone in a dev setup without users.
    admin: bool
    # Development mode (GAMEFLEET_DEV=true): API docs are served; the dashboard shows a banner.
    dev: bool


@router.post("/login", response_model=LoginResponse, operation_id="login")
def login(body: LoginRequest):
    """Exchange username and password for a bearer token."""
    if not auth.AUTH_ENABLED:
        raise HTTPException(status_code=400, detail="No users are configured (GAMEFLEET_USERS is not set)")
    user = auth.authenticate(body.username.strip(), body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Wrong username or password")
    token, expires_at = auth.create_token(user.name)
    return LoginResponse(token=token, username=user.name, expires_at=expires_at)


@router.get("/me", response_model=SessionInfo, operation_id="getSession")
async def me(user: auth.User | None = Depends(auth.optional_user)):
    """Who the caller is: a visitor, a logged-in user, or anyone with login disabled. 401 for a rejected token."""
    return SessionInfo(
        auth_enabled=auth.AUTH_ENABLED,
        username=user.name if user else None,
        admin=auth.OPEN_ACCESS or user is not None,
        dev=DEV,
    )
