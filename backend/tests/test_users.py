import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models.audit import AuditLog
from app.models.user import Role, User
from app.services.audit import AuditAction

USERS = "/api/v1/users"
ME = "/api/v1/auth/me"

NEW_USER = {
    "email": "Field.Worker@Example.com",
    "full_name": "Field Worker",
    "password": "a-strong-password-123",
    "role": "field_worker",
}


def test_admin_can_create_and_list_users(client, admin_headers, db):
    created = client.post(USERS, json=NEW_USER, headers=admin_headers)

    assert created.status_code == 201
    assert created.json()["email"] == "field.worker@example.com"
    assert created.json()["role"] == "field_worker"

    listed = client.get(USERS, headers=admin_headers).json()
    assert {u["email"] for u in listed} == {"admin@example.com", "field.worker@example.com"}

    audit = db.scalars(select(AuditLog).where(AuditLog.action == AuditAction.USER_CREATED)).all()
    assert len(audit) == 2  # the admin fixture + this user
    assert audit[-1].target_id == created.json()["id"]


@pytest.mark.parametrize("role", [Role.ANALYST, Role.FIELD_WORKER, Role.VIEWER])
def test_non_admins_cannot_manage_users(client, make_user, login, role):
    make_user("someone@example.com", role)
    headers = login("someone@example.com")

    assert client.get(USERS, headers=headers).status_code == 403
    assert client.post(USERS, json=NEW_USER, headers=headers).status_code == 403


def test_duplicate_email_is_rejected(client, admin_headers):
    assert client.post(USERS, json=NEW_USER, headers=admin_headers).status_code == 201
    again = client.post(USERS, json=NEW_USER, headers=admin_headers)
    assert again.status_code == 409


def test_short_password_is_rejected(client, admin_headers):
    response = client.post(USERS, json={**NEW_USER, "password": "short"}, headers=admin_headers)
    assert response.status_code == 422


def test_deactivation_revokes_existing_tokens(client, admin_headers, make_user, login):
    user = make_user("staff@example.com")
    staff_headers = login("staff@example.com")
    assert client.get(ME, headers=staff_headers).status_code == 200

    response = client.patch(f"{USERS}/{user.id}", json={"is_active": False}, headers=admin_headers)
    assert response.status_code == 200
    assert client.get(ME, headers=staff_headers).status_code == 401


def test_role_change_revokes_existing_tokens(client, admin_headers, make_user, login):
    user = make_user("staff@example.com", Role.VIEWER)
    old_headers = login("staff@example.com")

    client.patch(f"{USERS}/{user.id}", json={"role": "analyst"}, headers=admin_headers)

    assert client.get(ME, headers=old_headers).status_code == 401
    assert client.get(ME, headers=login("staff@example.com")).json()["role"] == "analyst"


def test_name_change_keeps_tokens_valid(client, admin_headers, make_user, login):
    user = make_user("staff@example.com")
    headers = login("staff@example.com")

    client.patch(f"{USERS}/{user.id}", json={"full_name": "New Name"}, headers=admin_headers)
    assert client.get(ME, headers=headers).status_code == 200


def test_last_admin_cannot_be_removed(client, admin_headers, db):
    admin = db.scalar(select(User).where(User.email == "admin@example.com"))

    demote = client.patch(f"{USERS}/{admin.id}", json={"role": "viewer"}, headers=admin_headers)
    deactivate = client.patch(
        f"{USERS}/{admin.id}", json={"is_active": False}, headers=admin_headers
    )
    assert demote.status_code == deactivate.status_code == 409


def test_second_admin_can_be_demoted(client, admin_headers, make_user):
    other = make_user("admin2@example.com", Role.ADMIN)

    response = client.patch(f"{USERS}/{other.id}", json={"role": "analyst"}, headers=admin_headers)
    assert response.status_code == 200


def test_update_is_audited_with_before_and_after(client, admin_headers, make_user, db):
    user = make_user("staff@example.com", Role.VIEWER)
    client.patch(f"{USERS}/{user.id}", json={"role": "analyst"}, headers=admin_headers)

    entry = db.scalar(select(AuditLog).where(AuditLog.action == AuditAction.USER_UPDATED))
    assert entry.details == {"changes": {"role": {"from": "viewer", "to": "analyst"}}}


def test_unknown_user_returns_404(client, admin_headers):
    response = client.patch(
        f"{USERS}/00000000-0000-0000-0000-000000000000",
        json={"full_name": "X"},
        headers=admin_headers,
    )
    assert response.status_code == 404


@pytest.mark.parametrize(
    "statement", ["UPDATE audit_log SET action = 'x'", "DELETE FROM audit_log"]
)
def test_audit_log_is_append_only(admin_headers, db, statement):
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text(statement))
    db.rollback()
