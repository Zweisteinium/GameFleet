import asyncio
import base64
import os
import time
from types import SimpleNamespace

os.environ["GAMEFLEET_SECRET"] = "test-secret-" + "x" * 40
os.environ["GAMEFLEET_USERS"] = "alice:wonderland,bob:builder"

from gamefleet_backend import auth, totp  # noqa: E402
from gamefleet_backend.services import account_service  # noqa: E402

RFC_KEY = b"12345678901234567890"


def run(coro):
    return asyncio.run(coro)


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
    assert auth.authenticate("alice", "wonderland") == auth.User("alice")
    assert auth.authenticate("alice", "wrong") is None
    assert auth.authenticate("nobody", "wonderland") is None
    assert auth.PLAIN_PASSWORDS == ["alice", "bob"]
    assert all(v.startswith(auth.HASH_PREFIX) for v in auth._CHECK.values())


def test_token_kinds_are_not_interchangeable():
    session, _ = auth.create_token("alice")
    challenge, _ = auth.create_challenge("alice")
    enrollment, _, nonce = auth.create_enrollment("alice")
    download, _ = auth.create_download_token("srv", "/data/backups/a.zip")
    assert auth.open_challenge(challenge) == (auth.CHALLENGE, "alice", None)
    assert auth.open_challenge(enrollment) == (auth.ENROLL, "alice", nonce)
    assert auth.open_challenge(session) is None
    assert auth.open_challenge(download) is None
    account_service._valid_after["alice"] = (0, time.monotonic())
    assert run(auth.verify_token(session)) == auth.User("alice")
    for other in (challenge, enrollment, download, "garbage", "a.b", session + "x"):
        assert run(auth.verify_token(other)) is None
    assert not auth.verify_download_token(session, "srv", "/data/backups/a.zip")
    assert auth.verify_download_token(download, "srv", "/data/backups/a.zip")
    assert not auth.verify_download_token(download, "srv", "/data/backups/b.zip")


def test_tokens_of_one_user_do_not_work_for_another():
    session, _ = auth.create_token("alice")
    payload, signature = session.split(".")
    forged = auth._b64(auth._unb64(payload).replace(b"alice", b"bob")) + "." + signature
    account_service._valid_after["bob"] = (0, time.monotonic())
    assert run(auth.verify_token(forged)) is None


def test_new_password_ends_sessions():
    session, _ = auth.create_token("alice")
    account_service._valid_after["alice"] = (0, time.monotonic())
    old = auth.USERS["alice"]
    try:
        auth.USERS["alice"] = "changed"
        assert run(auth.verify_token(session)) is None
    finally:
        auth.USERS["alice"] = old
    assert run(auth.verify_token(session)) == auth.User("alice")


def test_sign_out_everywhere_refuses_older_sessions():
    session, _ = auth.create_token("alice")
    account_service._valid_after["alice"] = (auth.now_ms() + 1, time.monotonic())
    assert run(auth.verify_token(session)) is None
    time.sleep(0.005)
    newer, _ = auth.create_token("alice")
    assert run(auth.verify_token(newer)) == auth.User("alice")


def test_expired_tokens():
    token, _ = auth._sign(auth.SESSION, "alice", [str(auth.now_ms())], -1)
    account_service._valid_after["alice"] = (0, time.monotonic())
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
