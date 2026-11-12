from typing import Optional

from sqlalchemy import BigInteger
from sqlmodel import Field, SQLModel


class UserSecurity(SQLModel, table=True):
    """Second factor and session state of a login from GAMEFLEET_USERS (the users themselves live there)."""
    username: str = Field(primary_key=True, max_length=100)
    # The authenticator key is never stored: it is HMAC(GAMEFLEET_SECRET, nonce), so a copy of the database
    # alone cannot produce codes. None = no authenticator set up yet; the next login sets one up.
    totp_nonce: Optional[str] = Field(default=None, max_length=64)
    # Last step whose code was accepted; codes of that step or earlier are refused (no replay).
    totp_last_step: int = Field(default=0, sa_type=BigInteger)
    # JSON list of HMACs of the unused recovery codes.
    recovery_codes: str = Field(default="[]")
    # Session tokens issued before this moment (milliseconds) are refused: "sign out everywhere".
    sessions_valid_after: int = Field(default=0, sa_type=BigInteger)
