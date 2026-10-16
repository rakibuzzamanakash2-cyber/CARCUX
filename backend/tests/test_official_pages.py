"""Official pages: admins create and verify them (by the office's email or a letter),
officials speak for one page, unverified and suspended pages stay hidden."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.audit import AuditLog
from app.models.user import Role, User
from app.services.audit import AuditAction

URL = "/api/v1/official-pages"
PMO = {
    "slug": "pmo", "name": "Prime Minister's Office", "name_bn": "প্রধানমন্ত্রীর কার্যালয়",
    "kind": "head_of_government", "website": "https://pmo.gov.bd",
    "contact_email": "Info@PMO.gov.bd",
}  # fmt: skip
LETTER = b"%PDF-1.7\n1 0 obj << >> endobj\n%%EOF"


@pytest.fixture
def staff(make_user, login):
    make_user("admin@office.local", Role.ADMIN)
    make_user("analyst@office.local", Role.ANALYST)
    return {"admin": login("admin@office.local"), "analyst": login("analyst@office.local")}


def _create(client, staff, **body):
    r = client.post(URL, json={**PMO, **body}, headers=staff["admin"])
    assert r.status_code == 201, r.text
    return r.json()


def test_only_admins_create_and_new_pages_are_hidden(client, staff):
    assert client.post(URL, json=PMO, headers=staff["analyst"]).status_code == 403
    page = _create(client, staff)
    assert page["status"] == "pending" and page["contact_email"] == "info@pmo.gov.bd"
    assert client.get(URL, headers=staff["analyst"]).json() == []
    assert client.get(f"{URL}/by-slug/pmo", headers=staff["analyst"]).status_code == 404
    assert [p["slug"] for p in client.get(URL, headers=staff["admin"]).json()] == ["pmo"]
    again = client.post(URL, json=PMO, headers=staff["admin"])
    assert again.status_code == 422 and "taken" in again.json()["detail"]
    bad = client.post(URL, json={**PMO, "slug": "PM Office!"}, headers=staff["admin"])
    assert bad.status_code == 422


def test_verification_needs_evidence(client, staff, db):
    page = _create(client, staff, contact_email=None)
    note = {"note": "Confirmed by phone with the PS and a reply from the office address"}
    by_email = client.post(f"{URL}/{page['id']}/verify", json={"method": "official_email", **note},
                           headers=staff["admin"])  # fmt: skip
    assert by_email.status_code == 422 and "email" in by_email.json()["detail"]
    by_letter = client.post(f"{URL}/{page['id']}/verify",
                            json={"method": "official_letter", **note},
                            headers=staff["admin"])  # fmt: skip
    assert by_letter.status_code == 422 and "letter" in by_letter.json()["detail"]

    fake = client.post(f"{URL}/{page['id']}/document", files={"file": ("x.pdf", b"not a pdf")},
                       headers=staff["admin"])  # fmt: skip
    assert fake.status_code == 422
    up = client.post(f"{URL}/{page['id']}/document",
                     files={"file": ("letter.pdf", LETTER, "application/pdf")},
                     headers=staff["admin"])  # fmt: skip
    assert up.status_code == 200 and up.json()["has_document"] is True
    ok = client.post(f"{URL}/{page['id']}/verify", json={"method": "official_letter", **note},
                     headers=staff["admin"])  # fmt: skip
    body = ok.json()
    assert ok.status_code == 200 and body["status"] == "verified"
    assert body["verified_by"]["full_name"] and body["verification_method"] == "official_letter"

    doc = client.get(f"{URL}/{page['id']}/document", headers=staff["admin"])
    assert doc.status_code == 200 and doc.content == LETTER
    assert client.get(f"{URL}/{page['id']}/document", headers=staff["analyst"]).status_code == 403

    # Everyone signed in sees the verified page, without how it was verified.
    seen = client.get(f"{URL}/by-slug/pmo", headers=staff["analyst"]).json()
    assert seen["status"] == "verified" and "verification_note" not in seen
    actions = set(db.scalars(select(AuditLog.action).where(AuditLog.target_id == page["id"])))
    assert {AuditAction.OFFICIAL_PAGE_CREATED, AuditAction.OFFICIAL_PAGE_DOCUMENT_ADDED,
            AuditAction.OFFICIAL_PAGE_VERIFIED} <= actions  # fmt: skip


def test_suspend_and_reinstate(client, staff):
    page = _create(client, staff)
    pid = page["id"]
    note = {"method": "official_email", "note": "Reply received from info@pmo.gov.bd on 16 Oct"}
    client.post(f"{URL}/{pid}/verify", json=note, headers=staff["admin"])
    r = client.post(f"{URL}/{pid}/suspend", json={"reason": "Office asked to pause the page"},
                    headers=staff["admin"])  # fmt: skip
    assert r.json()["status"] == "suspended"
    assert client.get(f"{URL}/by-slug/pmo", headers=staff["analyst"]).status_code == 404
    again = client.post(f"{URL}/{pid}/verify", json=note, headers=staff["admin"])
    assert again.status_code == 422
    back = client.post(f"{URL}/{pid}/reinstate", headers=staff["admin"]).json()
    assert back["status"] == "verified" and back["suspended_reason"] is None


def test_official_accounts(client, staff, login, db):
    page = _create(client, staff)
    member = {"email": "ps@pmo.gov.bd", "full_name": "Private Secretary",
              "password": "a-long-enough-password"}  # fmt: skip
    r = client.post(f"{URL}/{page['id']}/members", json=member, headers=staff["admin"])
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "official" and r.json()["official_page"]["slug"] == "pmo"
    official = login("ps@pmo.gov.bd", "a-long-enough-password")

    # Their own page, even before it is verified, with its members.
    mine = client.get(f"{URL}/mine", headers=official).json()
    assert mine["slug"] == "pmo" and [m["email"] for m in mine["members"]] == ["ps@pmo.gov.bd"]
    # Officials read the situation like viewers, and do not do analysts' work.
    assert client.get("/api/v1/events", headers=official).status_code == 200
    assert client.get("/api/v1/annotation/queue", headers=official).status_code == 403
    assert client.post(URL, json={**PMO, "slug": "x-y"}, headers=official).status_code == 403
    assert client.get(f"{URL}/mine", headers=staff["analyst"]).status_code == 404


def test_an_official_always_has_a_page(client, staff, db):
    users = "/api/v1/users"
    no_page = {"email": "o@x.gov.bd", "full_name": "O", "password": "a-long-enough-password",
               "role": "official"}  # fmt: skip
    assert client.post(users, json=no_page, headers=staff["admin"]).status_code == 422
    page = _create(client, staff)
    made = client.post(users, json={**no_page, "official_page_id": page["id"]},
                       headers=staff["admin"])  # fmt: skip
    assert made.status_code == 201
    uid = made.json()["id"]
    analyst_with_page = client.post(users, json={**no_page, "email": "a@x.org", "role": "analyst",
                                                 "official_page_id": page["id"]},
                                    headers=staff["admin"])  # fmt: skip
    assert analyst_with_page.status_code == 422
    # Leaving the official role drops the page; going back needs one.
    out = client.patch(f"{users}/{uid}", json={"role": "viewer"}, headers=staff["admin"]).json()
    assert out["role"] == "viewer" and out["official_page"] is None
    back = client.patch(f"{users}/{uid}", json={"role": "official"}, headers=staff["admin"])
    assert back.status_code == 422
    back = client.patch(f"{users}/{uid}", json={"role": "official", "official_page_id": page["id"]},
                        headers=staff["admin"])  # fmt: skip
    assert back.json()["official_page"]["id"] == page["id"]
    # The database refuses an official without a page, whatever the code does.
    user = db.get(User, __import__("uuid").UUID(uid))
    user.official_page_id = None
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
