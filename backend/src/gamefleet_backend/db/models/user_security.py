from typing import Optional

from sqlalchemy import BigInteger
from sqlmodel import Field, SQLModel


class UserSecurity(SQLModel, table=True):
    """Second factor and session state of a login. Users from GAMEFLEET_USERS keep their password there;
    invited users (``make invite``) keep it here, in ``password_hash``."""
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
    # scrypt hash of an invited user's password, set when the invite is accepted. None for users from
    # GAMEFLEET_USERS and for invites not accepted yet.
    password_hash: Optional[str] = Field(default=None, max_length=200)
    # Open invite: HMAC of the link's token (the token itself is not stored), its expiry in unix seconds, and
    # the password chosen on the invite page, which takes effect only once the authenticator is confirmed.
    invite_hash: Optional[str] = Field(default=None, max_length=64)
    invite_expires: int = Field(default=0, sa_type=BigInteger)
    invite_password: Optional[str] = Field(default=None, max_length=200)
