"""Two-factor sign-in with an authenticator app, and recovery codes."""

import base64

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import auth as auth_api
from app.core import totp
from app.core.config import Settings
from app.main import create_app
from app.models.audit import AuditLog
from app.models.user import Role, User
from tests.conftest import PASSWORD, TEST_DATABASE_URL

LOGIN = "/api/v1/auth/login"
TWO = "/api/v1/auth/two-factor"
EMAIL = "analyst@office.local"


class Clock:
    """The time the server sees, moved on by hand so codes do not repeat."""

    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now

    def step(self, seconds: float = 30):
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(auth_api.time, "time", c)
    return c


def code(secret: str, clock: Clock) -> str:
    return totp.code_at(secret, int(clock.now // totp.STEP))


def headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def enable(client, h, clock) -> tuple[str, list[str]]:
    setup = client.post(f"{TWO}/setup", headers=h).json()
    r = client.post(f"{TWO}/enable", json={"code": code(setup["secret"], clock)}, headers=h)
    assert r.status_code == 200, r.text
    return setup["secret"], r.json()["recovery_codes"]


def password_step(client, email=EMAIL):
    r = client.post(LOGIN, json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()


# --- The algorithm ---------------------------------------------------------------------------


def test_rfc_6238_test_vectors():
    # RFC 6238, appendix B (SHA-1 seed "12345678901234567890"), last 6 of the 8 digits.
    secret = base64.b32encode(b"12345678901234567890").decode()
    assert totp.code_at(secret, 59 // 30) == "287082"
    assert totp.code_at(secret, 1111111109 // 30) == "081804"
    assert totp.code_at(secret, 1234567890 // 30) == "005924"


def test_window_and_no_replay():
    secret, now = totp.new_secret(), 1_800_000_000.0
    current = int(now // 30)
    assert totp.verify(secret, totp.code_at(secret, current), now, None) == current
    assert totp.verify(secret, totp.code_at(secret, current - 1), now, None) == current - 1
    assert totp.verify(secret, totp.code_at(secret, current - 2), now, None) is None
    assert totp.verify(secret, totp.code_at(secret, current), now, current) is None  # used
    assert totp.verify(secret, "12 34", now, None) is None


def test_secrets_are_encrypted_with_the_server_key():
    a = Settings(environment="test", jwt_secret="x" * 40)
    b = Settings(environment="test", jwt_secret="y" * 40)
    sealed = totp.encrypt(a, "JBSWY3DPEHPK3PXP")
    assert "JBSWY3DPEHPK3PXP" not in sealed and totp.decrypt(a, sealed) == "JBSWY3DPEHPK3PXP"
    with pytest.raises(Exception):  # noqa: B017 (any failure: the key is wrong)
        totp.decrypt(b, sealed)


# --- Setting it up and signing in -------------------------------------------------------------


def test_set_up_then_sign_in_with_a_code(client, make_user, login, db, clock):
    make_user(EMAIL, Role.ANALYST)
    h = login(EMAIL)
    assert client.get(TWO, headers=h).json()["enabled"] is False
    setup = client.post(f"{TWO}/setup", headers=h).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/CARCUX:")
    assert setup["qr_svg"].lstrip().startswith("<?xml") or "<svg" in setup["qr_svg"]
    wrong = client.post(f"{TWO}/enable", json={"code": "000000"}, headers=h)
    assert wrong.status_code == 400
    r = client.post(f"{TWO}/enable", json={"code": code(setup["secret"], clock)}, headers=h)
    codes = r.json()["recovery_codes"]
    assert len(codes) == 10 and len(set(codes)) == 10
    stored = db.scalar(select(User).where(User.email == EMAIL))
    db.refresh(stored)
    assert setup["secret"] not in (stored.totp_secret or "")  # encrypted at rest
    assert not any(c in str(stored.recovery_codes) for c in codes)  # only hashes

    first = password_step(client)
    assert first["two_factor_required"] and first["access_token"] is None
    # The code that turned it on cannot be used again; the next one works.
    again = {"challenge": first["challenge"], "code": code(setup["secret"], clock)}
    assert client.post(f"{LOGIN}/two-factor", json=again).status_code == 401
    clock.step()
    ok = client.post(
        f"{LOGIN}/two-factor",
        json={"challenge": first["challenge"], "code": code(setup["secret"], clock)},
    )
    assert ok.status_code == 200 and ok.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers=headers(ok.json()["access_token"])).json()
    assert me["two_factor_enabled"] is True
    actions = db.scalars(select(AuditLog.action)).all()
    assert "auth.two_factor_enabled" in actions and "auth.two_factor_failed" in actions


def test_a_recovery_code_works_once(client, make_user, login, clock):
    make_user(EMAIL, Role.ANALYST)
    _, codes = enable(client, login(EMAIL), clock)
    challenge = password_step(client)["challenge"]
    r = client.post(f"{LOGIN}/two-factor", json={"challenge": challenge, "code": codes[0].upper()})
    assert r.status_code == 200
    challenge = password_step(client)["challenge"]
    r = client.post(f"{LOGIN}/two-factor", json={"challenge": challenge, "code": codes[0]})
    assert r.status_code == 401
    h = headers(
        client.post(f"{LOGIN}/two-factor", json={"challenge": challenge, "code": codes[1]}).json()[
            "access_token"
        ]
    )
    assert client.get(TWO, headers=h).json()["recovery_codes_left"] == 8


def test_wrong_codes_are_limited(client, make_user, login, clock):
    make_user(EMAIL, Role.ANALYST)
    secret, _ = enable(client, login(EMAIL), clock)
    challenge = password_step(client)["challenge"]
    for _ in range(5):
        r = client.post(f"{LOGIN}/two-factor", json={"challenge": challenge, "code": "111111"})
        assert r.status_code == 401
    clock.step()
    r = client.post(
        f"{LOGIN}/two-factor", json={"challenge": challenge, "code": code(secret, clock)}
    )
    assert r.status_code == 429


def test_challenges_expire_and_cannot_be_forged(client, make_user, login, clock):
    make_user(EMAIL, Role.ANALYST)
    h = login(EMAIL)
    secret, _ = enable(client, h, clock)
    clock.step()
    bad = client.post(f"{LOGIN}/two-factor", json={"challenge": "x" * 40, "code": "123456"})
    assert bad.status_code == 401
    # An access token is not a challenge.
    token = h["Authorization"].split()[1]
    r = client.post(f"{LOGIN}/two-factor", json={"challenge": token, "code": code(secret, clock)})
    assert r.status_code == 401


def test_turning_it_off_needs_password_and_code(client, make_user, login, clock):
    make_user(EMAIL, Role.ANALYST)
    h = login(EMAIL)
    secret, _ = enable(client, h, clock)
    clock.step()
    body = {"password": "wrong password!", "code": code(secret, clock)}
    assert client.post(f"{TWO}/disable", json=body, headers=h).status_code == 400
    body["password"] = PASSWORD
    assert client.post(f"{TWO}/disable", json=body, headers=h).status_code == 204
    assert client.get(TWO, headers=h).json()["enabled"] is False
    assert password_step(client)["access_token"]  # one step again


def test_new_recovery_codes_replace_the_old(client, make_user, login, clock):
    make_user(EMAIL, Role.ANALYST)
    h = login(EMAIL)
    secret, old = enable(client, h, clock)
    clock.step()
    new = client.post(
        f"{TWO}/recovery-codes", json={"code": code(secret, clock)}, headers=h
    ).json()["recovery_codes"]
    assert set(new).isdisjoint(old)
    challenge = password_step(client)["challenge"]
    r = client.post(f"{LOGIN}/two-factor", json={"challenge": challenge, "code": old[0]})
    assert r.status_code == 401


def test_admin_reset_signs_them_out(client, make_user, login, admin_headers, clock):
    user = make_user(EMAIL, Role.ANALYST)
    h = login(EMAIL)
    enable(client, h, clock)
    r = client.post(f"/api/v1/users/{user.id}/two-factor/reset", headers=admin_headers)
    assert r.status_code == 204
    assert client.get("/api/v1/auth/me", headers=h).status_code == 401  # signed out
    assert password_step(client)["access_token"]  # password alone again
    me = client.get("/api/v1/auth/me", headers=admin_headers).json()
    own = client.post(f"/api/v1/users/{me['id']}/two-factor/reset", headers=admin_headers)
    assert own.status_code == 400


# --- Required for some roles -----------------------------------------------------------------


@pytest.fixture
def strict(engine, tmp_path):
    settings = Settings(
        environment="test", database_url=TEST_DATABASE_URL, media_dir=tmp_path / "media",
        require_two_factor_roles=["admin", "analyst"],
    )  # fmt: skip
    with TestClient(create_app(settings)) as c:
        yield c


def test_required_roles_can_only_set_it_up_first(strict, make_user, clock):
    make_user(EMAIL, Role.ANALYST)
    make_user("worker@office.local", Role.FIELD_WORKER)
    h = headers(password_step(strict)["access_token"])
    me = strict.get("/api/v1/auth/me", headers=h).json()
    assert me["two_factor_setup_needed"] is True
    blocked = strict.get("/api/v1/events", headers=h)
    assert blocked.status_code == 403 and "two-factor" in blocked.json()["detail"]
    enable(strict, h, clock)
    assert strict.get("/api/v1/events", headers=h).status_code == 200
    # Required: cannot simply be turned off.
    clock.step()
    r = strict.post(f"{TWO}/disable", json={"password": PASSWORD, "code": "123456"}, headers=h)
    assert r.status_code == 403
    # Other roles are not affected.
    w = strict.post(LOGIN, json={"email": "worker@office.local", "password": PASSWORD}).json()
    assert (
        strict.get("/api/v1/field-reports", headers=headers(w["access_token"])).status_code == 200
    )


def test_production_requires_it_for_admins_and_analysts_by_default():
    s = Settings(environment="production", jwt_secret="z" * 40)
    assert s.two_factor_roles == {"admin", "analyst"}
    assert Settings(environment="development").two_factor_roles == frozenset()
    assert Settings(environment="production", jwt_secret="z" * 40,
                    require_two_factor_roles=[]).two_factor_roles == frozenset()  # fmt: skip
