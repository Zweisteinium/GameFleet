import asyncio
import base64
import os
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

os.environ["GAMEFLEET_SECRET"] = "test-secret-" + "x" * 40
os.environ["GAMEFLEET_USERS"] = "alice:wonderland,bob:builder"

from gamefleet_backend import auth, totp  # noqa: E402
from gamefleet_backend.db.models.user_security import UserSecurity  # noqa: E402
from gamefleet_backend.services import account_service  # noqa: E402

RFC_KEY = b"12345678901234567890"
PASSWORD = "correct horse battery"


def run(coro):
    return asyncio.run(coro)


class Accounts:
    """account_service without a database: rows in a dict, no caching."""

    def __init__(self):
        self.rows: dict[str, UserSecurity] = {}

    def row(self, name: str) -> UserSecurity:
        return self.rows.setdefault(name, UserSecurity(username=name))

    async def get(self, name):
        return self.rows.get(name) or UserSecurity(username=name)

    async def valid_after(self, name):
        return (await self.get(name)).sessions_valid_after

    async def password_hash(self, name):
        return (await self.get(name)).password_hash

    async def find_invite(self, digest):
        return next((r for r in self.rows.values() if r.invite_hash == digest), None)

    @asynccontextmanager
    async def locked(self, name):
        yield self.row(name)


@pytest.fixture(autouse=True)
def accounts(monkeypatch):
    fake = Accounts()
    for name in ("get", "valid_after", "password_hash", "find_invite", "locked"):
        monkeypatch.setattr(account_service, name, getattr(fake, name))
    return fake


def current_code(username: str, nonce: str) -> str:
    return totp.code_at(auth.totp_key(username, nonce), int(time.time()) // totp.STEP)


def test_rfc6238_vectors():
    # RFC 6238 appendix B (SHA-1), last six of the eight digits.
    for t, code in [(59, "287082"), (1111111109, "081804"), (1234567890, "005924"), (2000000000, "279037")]:
        assert totp.code_at(RFC_KEY, t // totp.STEP) == code


def test_match_window_and_replay():
    now = 1234567890
    step = now // totp.STEP
    assert totp.match(RFC_KEY, "005924", 0, now=now) == step
    assert totp.match(RFC_KEY, totp.code_at(RFC_KEY, step - 1), 0, now=now) == step - 1  # clock a bit behind
    assert totp.match(RFC_KEY, totp.code_at(RFC_KEY, step - 2), 0, now=now) is None  # too old
    assert totp.match(RFC_KEY, "005924", step, now=now) is None  # used once already
    assert totp.match(RFC_KEY, "005 924", 0, now=now) == step
    assert totp.match(RFC_KEY, "00592", 0, now=now) is None
    assert totp.match(RFC_KEY, "٠٠٥٩٢٤", 0, now=now) is None  # non-ASCII digits


def test_uri_and_recovery_codes():
    uri = totp.uri(RFC_KEY, "alice")
    # Built from RFC_KEY rather than spelled out: the base32 text is the public RFC 6238 test key,
    # but secret scanners report it as a leaked key.
    secret = base64.b32encode(RFC_KEY).decode().rstrip("=")
    assert uri.startswith(f"otpauth://totp/GameFleet%3Aalice?secret={secret}&issuer=GameFleet")
    code = totp.recovery_code()
    assert len(code) == 11 and code[5] == "-"
    assert totp.normalize_recovery(code.upper().replace("-", " ")) == code.replace("-", "")


def test_users_and_passwords():
    assert run(auth.authenticate("alice", "wonderland")) == auth.User("alice")
    assert run(auth.authenticate("alice", "wrong")) is None
    assert run(auth.authenticate("nobody", "wonderland")) is None
    assert auth.PLAIN_PASSWORDS == ["alice", "bob"]
    assert all(v.startswith(auth.HASH_PREFIX) for v in auth._CHECK.values())


def test_token_kinds_are_not_interchangeable():
    session, _ = run(auth.create_token("alice"))
    challenge, _ = run(auth.create_challenge("alice"))
    enrollment, _, nonce = run(auth.create_enrollment("alice"))
    download, _ = auth.create_download_token("srv", "/data/backups/a.zip")
    assert run(auth.open_challenge(challenge)) == (auth.CHALLENGE, "alice", None)
    assert run(auth.open_challenge(enrollment)) == (auth.ENROLL, "alice", nonce)
    assert run(auth.open_challenge(session)) is None
    assert run(auth.open_challenge(download)) is None
    assert run(auth.verify_token(session)) == auth.User("alice")
    for other in (challenge, enrollment, download, "garbage", "a.b", session + "x"):
        assert run(auth.verify_token(other)) is None
    assert not auth.verify_download_token(session, "srv", "/data/backups/a.zip")
    assert auth.verify_download_token(download, "srv", "/data/backups/a.zip")
    assert not auth.verify_download_token(download, "srv", "/data/backups/b.zip")


def test_tokens_of_one_user_do_not_work_for_another():
    session, _ = run(auth.create_token("alice"))
    payload, signature = session.split(".")
    forged = auth._b64(auth._unb64(payload).replace(b"alice", b"bob")) + "." + signature
    assert run(auth.verify_token(forged)) is None


def test_new_password_ends_sessions():
    session, _ = run(auth.create_token("alice"))
    old = auth.USERS["alice"]
    try:
        auth.USERS["alice"] = "changed"
        assert run(auth.verify_token(session)) is None
    finally:
        auth.USERS["alice"] = old
    assert run(auth.verify_token(session)) == auth.User("alice")


def test_sign_out_everywhere_refuses_older_sessions(accounts):
    session, _ = run(auth.create_token("alice"))
    accounts.row("alice").sessions_valid_after = auth.now_ms() + 1
    assert run(auth.verify_token(session)) is None
    time.sleep(0.005)
    newer, _ = run(auth.create_token("alice"))
    assert run(auth.verify_token(newer)) == auth.User("alice")


def test_expired_tokens():
    token, _ = run(auth._sign(auth.SESSION, "alice", [str(auth.now_ms())], -1))
    assert run(auth.verify_token(token)) is None


def test_derived_keys_differ_per_user_and_nonce():
    assert auth.totp_key("alice", "n1") != auth.totp_key("bob", "n1")
    assert auth.totp_key("alice", "n1") != auth.totp_key("alice", "n2")
    assert len(auth.totp_key("alice", "n1")) == 20
    assert auth.recovery_hash("alice", "abcde-fghjk") == auth.recovery_hash("alice", "ABCDE FGHJK")
    assert auth.recovery_hash("alice", "abcde-fghjk") != auth.recovery_hash("bob", "abcde-fghjk")


def request(peer: str, header: str | None = None):
    headers = {auth.CLIENT_HEADER: header} if header else {}
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers=headers)


def test_client_address_trusts_only_the_frontend():
    auth._frontend = (frozenset({"172.16.2.3"}), time.monotonic())
    assert run(auth.client_address(request("172.16.2.3", "203.0.113.7"))) == "203.0.113.7"
    assert run(auth.client_address(request("172.16.2.3", "not an ip"))) == "172.16.2.3"
    assert run(auth.client_address(request("192.168.178.50", "203.0.113.7"))) == "192.168.178.50"
    assert run(auth.client_address(request("172.16.2.3"))) == "172.16.2.3"


def test_limit_key_groups_ipv6_networks():
    assert auth.limit_key("2003:ed:2716:3b00:1:2:3:4") == "2003:ed:2716:3b00::/64"
    assert auth.limit_key("2003:ed:2716:3b00:ffff::9") == "2003:ed:2716:3b00::/64"
    assert auth.limit_key("::ffff:203.0.113.7") == "203.0.113.7"
    assert auth.limit_key("203.0.113.7") == "203.0.113.7"


def test_login_limit_and_memory_bound():
    auth._failures.clear()
    for _ in range(auth.LOGIN_ATTEMPTS):
        assert not auth.login_blocked("203.0.113.9")
        auth.login_failed("203.0.113.9")
    assert auth.login_blocked("203.0.113.9") > 0
    assert not auth.login_blocked("203.0.113.10")
    for i in range(auth.MAX_TRACKED + 50):
        auth.login_failed(f"flood-{i}")
    assert len(auth._failures) <= auth.MAX_TRACKED
    auth._failures.clear()


def test_second_factor_lock_doubles():
    auth._factor_failures.clear()
    for _ in range(auth.FACTOR_ATTEMPTS):
        assert not auth.factor_blocked("alice")
        auth.factor_failed("alice")
    first = auth.factor_blocked("alice")
    assert auth.FACTOR_LOCK - 5 <= first <= auth.FACTOR_LOCK + 1
    failures, _, lockouts = auth._factor_failures["alice"]
    auth._factor_failures["alice"] = (failures, 0.0, lockouts)  # let the lock run out
    for _ in range(auth.FACTOR_ATTEMPTS):
        auth.factor_failed("alice")
    assert auth.factor_blocked("alice") > first * 1.9
    auth.factor_succeeded("alice")
    assert not auth.factor_blocked("alice")


def test_invite_sets_password_and_authenticator_together(accounts):
    token, expires_at = run(auth.create_invite("carol"))
    assert expires_at - time.time() > (auth.INVITE_HOURS - 1) * 3600
    assert run(auth.open_invite(token))[0] == "carol"
    assert run(auth.open_invite(token + "x")) is None
    with pytest.raises(auth.InviteError):
        run(auth.accept_invite(token, "short"))
    with pytest.raises(auth.InviteError):
        run(auth.accept_invite(token, "Carol     "))
    username, challenge, _, nonce = run(auth.accept_invite(token, PASSWORD))
    assert username == "carol"
    assert run(auth.open_challenge(challenge)) == (auth.INVITE, "carol", nonce)
    # Nothing works before the first code: no password, no session.
    assert run(auth.authenticate("carol", PASSWORD)) is None
    with pytest.raises(ValueError):
        run(auth.create_token("carol"))
    code = current_code("carol", nonce)
    wrong = f"{(int(code) + 500000) % 1000000:06d}"
    assert run(auth.finish_invite("carol", nonce, wrong)) is None
    codes = run(auth.finish_invite("carol", nonce, code))
    assert len(codes) == totp.RECOVERY_COUNT
    assert run(auth.authenticate("carol", PASSWORD)) == auth.User("carol")
    assert run(auth.security_state("carol")) == (True, totp.RECOVERY_COUNT)
    # The link and its challenge are used up.
    assert run(auth.open_invite(token)) is None
    assert run(auth.open_challenge(challenge)) is None
    with pytest.raises(auth.InviteError):
        run(auth.finish_invite("carol", nonce, code))
    session, _ = run(auth.create_token("carol"))
    assert run(auth.verify_token(session)) == auth.User("carol")
    # Removing the user ends the session.
    del accounts.rows["carol"]
    assert run(auth.verify_token(session)) is None


def test_new_invite_replaces_the_old_one_and_keeps_the_password_until_used(accounts):
    first, _ = run(auth.create_invite("dave"))
    _, challenge, _, nonce = run(auth.accept_invite(first, PASSWORD))
    run(auth.finish_invite("dave", nonce, current_code("dave", nonce)))
    session, _ = run(auth.create_token("dave"))
    second, _ = run(auth.create_invite("dave"))
    third, _ = run(auth.create_invite("dave"))
    assert run(auth.open_invite(second)) is None
    _, challenge, _, nonce = run(auth.accept_invite(third, "another long password"))
    # Until the new authenticator is confirmed, the old password and session still work.
    assert run(auth.authenticate("dave", PASSWORD)) == auth.User("dave")
    assert run(auth.verify_token(session)) == auth.User("dave")
    run(auth.create_invite("dave"))  # replaced once more: the pending challenge dies with it
    assert run(auth.open_challenge(challenge)) is None
    with pytest.raises(auth.InviteError):
        run(auth.finish_invite("dave", nonce, current_code("dave", nonce)))


def test_new_password_from_invite_ends_sessions(accounts):
    token, _ = run(auth.create_invite("erin"))
    _, _, _, nonce = run(auth.accept_invite(token, PASSWORD))
    run(auth.finish_invite("erin", nonce, current_code("erin", nonce)))
    session, _ = run(auth.create_token("erin"))
    token, _ = run(auth.create_invite("erin"))
    _, _, _, nonce = run(auth.accept_invite(token, "another long password"))
    time.sleep(0.002)
    run(auth.finish_invite("erin", nonce, current_code("erin", nonce)))
    assert run(auth.verify_token(session)) is None
    assert run(auth.authenticate("erin", PASSWORD)) is None
    assert run(auth.authenticate("erin", "another long password")) == auth.User("erin")


def test_expired_invite(accounts):
    token, _ = run(auth.create_invite("frank"))
    _, challenge, _, _ = run(auth.accept_invite(token, PASSWORD))
    accounts.row("frank").invite_expires = int(time.time()) - 1
    assert run(auth.open_invite(token)) is None
    assert run(auth.accept_invite(token, PASSWORD)) is None
    assert run(auth.open_challenge(challenge)) is None


def test_invite_names(accounts):
    for name in ("alice", "", "bad|name", "has space", "-dash", "x" * 33):
        with pytest.raises(auth.InviteError):
            run(auth.create_invite(name))
    assert not accounts.rows
    run(auth.create_invite("Player_1.x"))
