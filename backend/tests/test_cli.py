from sqlalchemy import select

from app import cli
from app.core.config import get_settings
from app.models.audit import AuditLog
from app.models.user import Role, User
from app.services.audit import AuditAction
from tests.conftest import TEST_DATABASE_URL


def _run(monkeypatch, passwords, email="boss@example.com"):
    monkeypatch.setenv("CARCUX_DATABASE_URL", TEST_DATABASE_URL)
    get_settings.cache_clear()
    answers = iter(passwords)
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: next(answers))
    try:
        return cli.main(["create-admin", "--email", email, "--name", "Boss"])
    finally:
        get_settings.cache_clear()


def test_create_admin(monkeypatch, engine, db):
    assert _run(monkeypatch, ["a-strong-password!", "a-strong-password!"]) == 0

    user = db.scalar(select(User).where(User.email == "boss@example.com"))
    assert user.role == Role.ADMIN
    entry = db.scalar(select(AuditLog).where(AuditLog.target_id == str(user.id)))
    assert entry.action == AuditAction.USER_BOOTSTRAPPED
    assert entry.actor_id is None


def test_create_admin_rejects_mismatch_and_short_password(monkeypatch, engine, db):
    assert _run(monkeypatch, ["a-strong-password!", "different-password"]) == 1
    assert _run(monkeypatch, ["short"]) == 1
    assert db.scalar(select(User)) is None


def test_create_admin_rejects_existing_email(monkeypatch, engine):
    assert _run(monkeypatch, ["a-strong-password!", "a-strong-password!"]) == 0
    assert _run(monkeypatch, ["a-strong-password!", "a-strong-password!"]) == 1


def test_cli_admin_with_internal_domain_can_log_in(monkeypatch, client):
    # Regression: the CLI used to accept emails the login endpoint then rejected.
    assert _run(monkeypatch, ["a-strong-password!"] * 2, email="Rakib@CARCUX.local") == 0

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "rakib@carcux.local", "password": "a-strong-password!"},
    )
    assert response.status_code == 200


def test_cli_rejects_malformed_email(monkeypatch, engine, db):
    assert _run(monkeypatch, [], email="not-an-email") == 1
    assert db.scalar(select(User)) is None
