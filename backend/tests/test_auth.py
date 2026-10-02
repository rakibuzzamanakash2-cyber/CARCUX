from sqlalchemy import select

from app.models.audit import AuditLog
from app.services.audit import AuditAction
from tests.conftest import PASSWORD

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"


def test_login_returns_token_and_me_works(client, make_user):
    make_user("staff@example.com")

    response = client.post(LOGIN, json={"email": "staff@example.com", "password": PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0

    me = client.get(ME, headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "staff@example.com"
    assert "password_hash" not in me.json()


def test_login_email_is_case_insensitive(client, make_user):
    make_user("staff@example.com")

    response = client.post(LOGIN, json={"email": "Staff@Example.COM", "password": PASSWORD})
    assert response.status_code == 200


def test_wrong_password_and_unknown_email_look_identical(client, make_user):
    make_user("staff@example.com")

    wrong = client.post(LOGIN, json={"email": "staff@example.com", "password": "nope"})
    unknown = client.post(LOGIN, json={"email": "ghost@example.com", "password": "nope"})

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Invalid email or password"}


def test_inactive_user_cannot_log_in(client, make_user):
    make_user("gone@example.com", is_active=False)

    response = client.post(LOGIN, json={"email": "gone@example.com", "password": PASSWORD})
    assert response.status_code == 401


def test_logins_are_audited(client, make_user, db):
    user = make_user("staff@example.com")
    client.post(LOGIN, json={"email": "staff@example.com", "password": "nope"})
    client.post(LOGIN, json={"email": "staff@example.com", "password": PASSWORD})

    rows = db.scalars(
        select(AuditLog).where(AuditLog.actor_id == user.id).order_by(AuditLog.id)
    ).all()
    assert [r.action for r in rows] == [AuditAction.LOGIN_FAILED, AuditAction.LOGIN_SUCCEEDED]
    assert rows[0].details == {"reason": "wrong_password"}
    # The password itself is never logged.
    assert all(PASSWORD not in str(r.details) for r in rows)


def test_me_requires_a_valid_token(client):
    assert client.get(ME).status_code == 401
    assert client.get(ME, headers={"Authorization": "Bearer not-a-token"}).status_code == 401


def test_oversized_password_is_rejected_before_hashing(client):
    response = client.post(LOGIN, json={"email": "a@example.com", "password": "x" * 10_000})
    assert response.status_code == 422
