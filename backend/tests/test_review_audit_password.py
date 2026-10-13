from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.user import Role, User
from app.services.audit import AuditAction
from tests.conftest import PASSWORD
from tests.test_field_reports import DHAKA, submit

REPORTS = "/api/v1/field-reports"


@pytest.fixture
def worker(make_user, login):
    make_user("worker@office.local", Role.FIELD_WORKER, full_name="Field Worker")
    return login("worker@office.local")


@pytest.fixture
def analyst(make_user, login):
    make_user("analyst@office.local", Role.ANALYST, full_name="Ana Analyst")
    return login("analyst@office.local")


# --- Review -----------------------------------------------------------------------------


def test_review_dismiss_and_reopen(client, analyst, worker, db):
    r = submit(client, worker).json()

    reviewed = client.post(
        f"{REPORTS}/{r['id']}/review", json={"status": "reviewed"}, headers=analyst
    )
    assert reviewed.status_code == 200, reviewed.text
    body = reviewed.json()
    assert body["status"] == "reviewed"
    assert body["reviewed_by"]["full_name"] == "Ana Analyst"
    assert body["reviewed_at"] is not None

    dismissed = client.post(
        f"{REPORTS}/{r['id']}/review",
        json={"status": "dismissed", "note": "  Duplicate of an earlier report  "},
        headers=analyst,
    ).json()
    assert (dismissed["status"], dismissed["review_note"]) == (
        "dismissed",
        "Duplicate of an earlier report",
    )

    reopened = client.post(
        f"{REPORTS}/{r['id']}/review", json={"status": "submitted"}, headers=analyst
    )
    assert reopened.json()["reviewed_by"] is None

    entries = db.scalars(
        select(AuditLog.details).where(AuditLog.action == AuditAction.FIELD_REPORT_REVIEWED)
    ).all()
    assert [(d["from"], d["to"]) for d in entries] == [
        ("submitted", "reviewed"),
        ("reviewed", "dismissed"),
        ("dismissed", "submitted"),
    ]


def test_dismiss_needs_a_reason(client, analyst, worker):
    r = submit(client, worker).json()
    for note in (None, "   "):
        response = client.post(
            f"{REPORTS}/{r['id']}/review",
            json={"status": "dismissed", "note": note},
            headers=analyst,
        )
        assert response.status_code == 422
        assert "Say why" in response.text


def test_only_reviewers_review(client, worker):
    r = submit(client, worker).json()
    response = client.post(
        f"{REPORTS}/{r['id']}/review", json={"status": "reviewed"}, headers=worker
    )
    assert response.status_code == 403


def test_queue_filters_status_and_oldest_first(client, analyst, worker):
    first = submit(client, worker).json()
    second = submit(client, worker, latitude=23.81).json()
    third = submit(client, worker, latitude=23.82).json()
    client.post(f"{REPORTS}/{second['id']}/review", json={"status": "reviewed"}, headers=analyst)

    queue = client.get(
        REPORTS, params={"status": "submitted", "order": "oldest"}, headers=analyst
    ).json()

    assert [i["id"] for i in queue["items"]] == [first["id"], third["id"]]


# --- Audit log --------------------------------------------------------------------------


def test_audit_log_for_admins_with_filters(client, admin_headers, analyst, worker):
    r = submit(client, worker).json()
    client.post(f"{REPORTS}/{r['id']}/review", json={"status": "reviewed"}, headers=analyst)

    everything = client.get("/api/v1/audit", headers=admin_headers).json()
    assert everything["total"] >= 4  # logins, submission, review
    assert "field_report.reviewed" in everything["actions"]
    newest = everything["items"][0]
    assert newest["action"] == "field_report.reviewed"
    assert newest["actor"]["full_name"] == "Ana Analyst"

    logins = client.get("/api/v1/audit", params={"action": "auth."}, headers=admin_headers).json()
    assert {i["action"] for i in logins["items"]} == {"auth.login_succeeded"}

    on_report = client.get(
        "/api/v1/audit", params={"target_id": r["id"]}, headers=admin_headers
    ).json()
    assert [i["action"] for i in on_report["items"]] == [
        "field_report.reviewed",
        "field_report.submitted",
    ]

    future = (datetime.now(DHAKA) + timedelta(days=1)).isoformat()
    assert (
        client.get("/api/v1/audit", params={"since": future}, headers=admin_headers).json()["total"]
        == 0
    )
    naive = client.get(
        "/api/v1/audit", params={"since": "2026-10-01T00:00:00"}, headers=admin_headers
    )
    assert naive.status_code == 422


def test_audit_log_is_admin_only(client, analyst):
    assert client.get("/api/v1/audit", headers=analyst).status_code == 403


# --- Passwords --------------------------------------------------------------------------


def test_change_own_password_signs_out_other_sessions(client, worker, login, db):
    new = "a-new-long-password-1"
    response = client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": new},
        headers=worker,
    )
    assert response.status_code == 200, response.text
    fresh = {"Authorization": f"Bearer {response.json()['access_token']}"}

    assert client.get("/api/v1/auth/me", headers=worker).status_code == 401  # old token revoked
    assert client.get("/api/v1/auth/me", headers=fresh).status_code == 200
    assert login("worker@office.local", new)
    assert db.scalar(select(AuditLog).where(AuditLog.action == AuditAction.PASSWORD_CHANGED))


@pytest.mark.parametrize(
    ("body", "code", "message"),
    [
        ({"current_password": "wrong-password-123", "new_password": "x" * 12}, 400, "incorrect"),
        ({"current_password": PASSWORD, "new_password": "short"}, 422, "at least 12"),
        ({"current_password": PASSWORD, "new_password": PASSWORD}, 422, "different"),
    ],
)
def test_change_password_rejections(client, worker, body, code, message):
    response = client.post("/api/v1/auth/password", json=body, headers=worker)
    assert response.status_code == code
    assert message in response.text


def test_admin_resets_a_password(client, admin_headers, worker, login, db):
    user = db.scalar(select(User).where(User.email == "worker@office.local"))

    response = client.post(
        f"/api/v1/users/{user.id}/password",
        json={"new_password": "temporary-password-9"},
        headers=admin_headers,
    )

    assert response.status_code == 204
    assert client.get("/api/v1/auth/me", headers=worker).status_code == 401
    assert login("worker@office.local", "temporary-password-9")
    assert db.scalar(select(AuditLog).where(AuditLog.action == AuditAction.PASSWORD_RESET))


def test_password_reset_is_admin_only(client, analyst, worker, db):
    user = db.scalar(select(User).where(User.email == "worker@office.local"))
    response = client.post(
        f"/api/v1/users/{user.id}/password",
        json={"new_password": "temporary-password-9"},
        headers=analyst,
    )
    assert response.status_code == 403
