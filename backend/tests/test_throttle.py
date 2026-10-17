"""Rate limits on sign-in, password checks, sign-up and field-report submissions."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.api.deps import client_ip
from app.core.config import Settings
from app.models.audit import AuditLog
from app.models.throttle import ThrottleEvent
from app.models.user import Role
from app.services import throttle
from tests.conftest import PASSWORD
from tests.test_field_reports import submit
from tests.test_public import P, _person

LOGIN = "/api/v1/auth/login"


def _login(client, email, password):
    return client.post(LOGIN, json={"email": email, "password": password})


def test_five_wrong_passwords_lock_even_the_right_one(client, make_user, db):
    make_user("analyst@office.local", Role.ANALYST)
    for _ in range(5):
        assert _login(client, "analyst@office.local", "wrong password!").status_code == 401
    locked = _login(client, "analyst@office.local", PASSWORD)
    assert locked.status_code == 429
    assert "Try again in 15 minutes" in locked.json()["detail"]
    assert 800 < int(locked.headers["Retry-After"]) <= 901
    actions = db.scalars(select(AuditLog.action)).all()
    assert actions.count("auth.login_failed") == 5 and "auth.login_throttled" in actions


def test_unknown_emails_are_limited_the_same_way(client):
    # Otherwise a lock-out would reveal which emails have accounts.
    for _ in range(5):
        assert _login(client, "nobody@office.local", "whatever pw").status_code == 401
    assert _login(client, "nobody@office.local", "whatever pw").status_code == 429


def test_a_successful_sign_in_forgets_earlier_mistakes(client, make_user):
    make_user("analyst@office.local", Role.ANALYST)
    for _ in range(4):
        _login(client, "analyst@office.local", "wrong password!")
    assert _login(client, "analyst@office.local", PASSWORD).status_code == 200
    for _ in range(4):
        _login(client, "analyst@office.local", "wrong password!")
    assert _login(client, "analyst@office.local", PASSWORD).status_code == 200


def test_other_accounts_are_not_affected(client, make_user):
    make_user("analyst@office.local", Role.ANALYST)
    for _ in range(5):
        _login(client, "nobody@office.local", "whatever pw")
    assert _login(client, "analyst@office.local", PASSWORD).status_code == 200


def test_changing_password_limits_guesses_of_the_current_one(client, make_user, login):
    make_user("analyst@office.local", Role.ANALYST)
    h = login("analyst@office.local")
    body = {"current_password": "not it at all", "new_password": "a brand new password"}
    for _ in range(5):
        assert client.post("/api/v1/auth/password", json=body, headers=h).status_code == 400
    body["current_password"] = PASSWORD
    assert client.post("/api/v1/auth/password", json=body, headers=h).status_code == 429


def test_public_sign_in_and_sign_up_are_limited(client, setup):  # noqa: F811
    _person(client)  # one sign-up
    for _ in range(5):
        r = client.post(
            f"{P}/auth/login", json={"email": "rina@example.com", "password": "nope nope"}
        )
        assert r.status_code == 401
    r = client.post(
        f"{P}/auth/login", json={"email": "rina@example.com", "password": "correct horse"}
    )
    assert r.status_code == 429
    for i in range(4):
        body = {
            "email": f"p{i}@example.com",
            "display_name": f"Person {i}",
            "password": "pw pw pw pw",
        }
        assert client.post(f"{P}/auth/signup", json=body).status_code == 202
    body = {"email": "p9@example.com", "display_name": "Person 9", "password": "pw pw pw pw"}
    assert client.post(f"{P}/auth/signup", json=body).status_code == 429


def test_field_report_submissions_are_limited(client, make_user, login, monkeypatch):
    monkeypatch.setitem(
        throttle.LIMITS, throttle.FIELD_REPORT, (throttle.Limit("key", 2, timedelta(minutes=10)),)
    )
    make_user("worker@office.local", Role.FIELD_WORKER)
    w = login("worker@office.local")
    assert submit(client, w).status_code == 201
    assert submit(client, w).status_code == 201
    assert submit(client, w).status_code == 429


def test_limits_expire_with_their_window(db):
    old = datetime.now(UTC) - timedelta(minutes=16)
    for _ in range(5):
        db.add(ThrottleEvent(kind=throttle.STAFF_LOGIN, key="k", ip="1.2.3.4", at=old))
    db.commit()
    throttle.check(db, throttle.STAFF_LOGIN, key="k", ip="1.2.3.4")  # no error
    for _ in range(5):
        throttle.record(db, throttle.STAFF_LOGIN, key="k", ip="1.2.3.4")
    db.commit()
    with pytest.raises(throttle.TooManyAttemptsError):
        throttle.check(db, throttle.STAFF_LOGIN, key="k", ip="1.2.3.4")
    # Another address with the same email: only the per-email limit (20 an hour) applies.
    throttle.check(db, throttle.STAFF_LOGIN, key="k", ip="5.6.7.8")


def test_keys_are_not_emails():
    s = Settings(environment="test")
    k = throttle.key_for(s, " Rina@Example.com ")
    assert k == throttle.key_for(s, "rina@example.com") and "rina" not in k and len(k) == 64


def _request(peer, forwarded=None, trust=True):
    headers = {"x-forwarded-for": forwarded} if forwarded else {}
    app = SimpleNamespace(state=SimpleNamespace(settings=Settings(
        environment="test", trust_forwarded_from_private=trust)))  # fmt: skip
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers=headers, app=app)


def test_client_address_from_the_frontend():
    # The frontend container (private address) passes the browser's address on.
    assert client_ip(_request("172.18.0.5", "203.0.113.7")) == "203.0.113.7"
    # Only the last entry counts: earlier ones are whatever the browser sent.
    assert client_ip(_request("172.18.0.5", "1.1.1.1, 203.0.113.7")) == "203.0.113.7"
    # Not believed from a public address, when switched off, or when it is not an address.
    assert client_ip(_request("8.8.8.8", "203.0.113.7")) == "8.8.8.8"
    assert client_ip(_request("172.18.0.5", "203.0.113.7", trust=False)) == "172.18.0.5"
    assert client_ip(_request("127.0.0.1", "not-an-ip")) == "127.0.0.1"
    assert client_ip(_request("127.0.0.1")) == "127.0.0.1"


from tests.test_statements import setup  # noqa: E402, F401 (fixture)
