"""Time-based one-time passwords (RFC 6238, the codes of Google Authenticator, Aegis, 1Password and the like)
and single-use recovery codes. Only the standard library: HMAC-SHA1, 30-second steps, six digits."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from typing import Optional
from urllib.parse import quote

STEP = 30
DIGITS = 6
# Steps accepted on either side of the current one, for clocks that are a little off.
WINDOW = 1

# Recovery codes: no 0/o, 1/l/i, so they can be read off paper.
RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
RECOVERY_LENGTH = 10  # about 50 bits
RECOVERY_COUNT = 10


def secret_text(key: bytes) -> str:
    """The key as authenticator apps take it: base32 without padding."""
    return base64.b32encode(key).decode().rstrip("=")


def code_at(key: bytes, step: int) -> str:
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** DIGITS).zfill(DIGITS)


def is_code(text: str) -> bool:
    return len(text) == DIGITS and text.isascii() and text.isdigit()


def match(key: bytes, code: str, after_step: int, now: Optional[float] = None) -> Optional[int]:
    """The step `code` belongs to, or None. Steps up to `after_step` are refused, so a code that was used once
    cannot be used again (replay)."""
    code = code.strip().replace(" ", "")
    if not is_code(code):
        return None
    current = int((time.time() if now is None else now) // STEP)
    found = None
    for step in range(current - WINDOW, current + WINDOW + 1):
        # Check every step, not just until the first hit, so the timing does not tell which one matched.
        if hmac.compare_digest(code_at(key, step), code) and step > after_step:
            found = step
    return found


def uri(key: bytes, account: str, issuer: str = "GameFleet") -> str:
    """The otpauth:// link that the QR code carries."""
    label = quote(f"{issuer}:{account}", safe="")
    return (f"otpauth://totp/{label}?secret={secret_text(key)}&issuer={quote(issuer, safe='')}"
            f"&algorithm=SHA1&digits={DIGITS}&period={STEP}")


def recovery_code() -> str:
    raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(RECOVERY_LENGTH))
    return f"{raw[:5]}-{raw[5:]}"


def normalize_recovery(text: str) -> str:
    return "".join(c for c in text.lower() if c.isalnum())
