"""Official statements: written by officials of verified pages from CARCUX's brief,
kept with that brief, marked as informed by CARCUX, never edited (a correction is a
new statement), hidden when the page is suspended."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.models.statement import Statement
from app.models.user import Role
from tests.test_assessment import _event, _report

PAGES = "/api/v1/official-pages"
URL = "/api/v1/statements"
PASSWORD = "a-long-enough-password"


@pytest.fixture
def setup(client, db, make_user, login):
    make_user("admin@office.local", Role.ADMIN)
    analyst = make_user("analyst@office.local", Role.ANALYST)
    worker = make_user("worker@office.local", Role.FIELD_WORKER, full_name="Karim Uddin")
    h = {"admin": login("admin@office.local"), "analyst": login("analyst@office.local")}
    page = client.post(
        PAGES, json={"slug": "ddm", "name": "Department of Disaster Management",
                     "kind": "department", "contact_email": "info@ddm.gov.bd"},
        headers=h["admin"],
    ).json()  # fmt: skip
    client.post(f"{PAGES}/{page['id']}/members", headers=h["admin"],
                json={"email": "desk@ddm.gov.bd", "full_name": "Desk Officer",
                      "password": PASSWORD})  # fmt: skip
    h["official"] = login("desk@ddm.gov.bd", PASSWORD)
    event = _event(db, analyst)
    _report(db, event, worker, analyst, text="Mirpur 10 e pani, 3 jon mara geche")
    db.commit()
    return {"h": h, "page": page, "event": event}


def _verify(client, setup):
    note = {"method": "official_email", "note": "Reply from info@ddm.gov.bd"}
    r = client.post(f"{PAGES}/{setup['page']['id']}/verify", headers=setup["h"]["admin"], json=note)
    assert r.status_code == 200


def _publish(client, setup, **body):
    payload = {
        "event_id": str(setup["event"].id),
        "finding": "confirmed",
        "title": "Waterlogging at Mirpur 10",
        "body": "Teams are on site. Three deaths are confirmed by the district office.",
    }
    return client.post(URL, json={**payload, **body}, headers=setup["h"]["official"])


def test_only_officials_of_verified_pages_publish(client, setup):
    assert _publish(client, setup).status_code == 403  # page not verified yet
    assert client.post(URL, json={}, headers=setup["h"]["analyst"]).status_code in (403, 422)
    _verify(client, setup)
    r = _publish(client, setup)
    assert r.status_code == 201, r.text
    st = r.json()
    assert st["informed_by_carcux"] is True and st["page"]["slug"] == "ddm"
    assert st["author"] == "Desk Officer"
    analyst_view = client.get(f"{URL}/{st['id']}", headers=setup["h"]["analyst"]).json()
    assert analyst_view["author"] is None  # the office speaks, not the person


def test_the_brief_names_public_sources_but_not_field_workers(client, setup):
    _verify(client, setup)
    b = client.get(f"/api/v1/events/{setup['event'].id}/brief", headers=setup["h"]["official"])
    assert b.status_code == 200, b.text
    brief = b.json()
    assert brief["suggestion"]["sources_supporting"] == 1
    assert brief["sources"][0]["source"] == "A field worker" and brief["field_workers"] == 1
    assert "Karim" not in str(brief)
    assert ("casualty_count", 3) in {(d["attribute"], d["estimate"]) for d in brief["details"]}
    # Kept with the statement as the official saw it.
    st = _publish(client, setup).json()
    assert st["brief"]["suggestion"] == brief["suggestion"] and "Karim" not in str(st)
    # Viewers and field workers do not get briefs.
    assert client.get(f"/api/v1/events/{setup['event'].id}/brief").status_code == 401


def test_corrections_are_new_statements(client, setup, db):
    _verify(client, setup)
    first = _publish(client, setup).json()
    fix = _publish(client, setup, finding="partly_confirmed", supersedes_id=first["id"],
                   title="Correction: two deaths, not three",
                   body="The district office has revised the count to two deaths.")  # fmt: skip
    assert fix.status_code == 201
    again = _publish(client, setup, supersedes_id=first["id"])
    assert again.status_code == 422 and "latest" in again.json()["detail"]
    old = client.get(f"{URL}/{first['id']}", headers=setup["h"]["analyst"]).json()
    assert old["superseded_by_id"] == fix.json()["id"]
    listed = client.get(URL, params={"event_id": str(setup["event"].id)},
                        headers=setup["h"]["analyst"]).json()  # fmt: skip
    assert [s["title"][:10] for s in listed] == ["Correction", "Waterloggi"]
    # Never edited or deleted, whatever the code does.
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE statements SET body = 'changed'"))
        db.commit()
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM statements"))
        db.commit()
    db.rollback()
    assert db.query(Statement).count() == 2


def test_other_pages_cannot_correct_and_suspension_hides(client, setup, login):
    _verify(client, setup)
    st = _publish(client, setup).json()
    h = setup["h"]
    other = client.post(PAGES, headers=h["admin"], json={
        "slug": "dncc", "name": "Dhaka North City Corporation", "kind": "city_corporation",
        "contact_email": "info@dncc.gov.bd"}).json()  # fmt: skip
    note = {"method": "official_email", "note": "Reply from info@dncc.gov.bd"}
    client.post(f"{PAGES}/{other['id']}/verify", headers=h["admin"], json=note)
    member = {"email": "pr@dncc.gov.bd", "full_name": "PR", "password": PASSWORD}
    client.post(f"{PAGES}/{other['id']}/members", headers=h["admin"], json=member)
    dncc = login("pr@dncc.gov.bd", PASSWORD)
    r = client.post(URL, headers=dncc, json={
        "event_id": str(setup["event"].id), "finding": "denied", "title": "Not true at all",
        "body": "Nothing happened at Mirpur 10 today.", "supersedes_id": st["id"]})  # fmt: skip
    assert r.status_code == 422  # another page cannot correct DDM's statement

    client.post(f"{PAGES}/{setup['page']['id']}/suspend", headers=h["admin"],
                json={"reason": "Paused at the office's request"})  # fmt: skip
    assert client.get(f"{URL}/{st['id']}", headers=h["analyst"]).status_code == 404
    assert client.get(URL, headers=h["analyst"]).json() == []
    assert client.get(f"{URL}/{st['id']}", headers=h["official"]).status_code == 200
    assert _publish(client, setup).status_code == 403  # suspended pages cannot publish
    assert client.get(f"{URL}/{uuid.uuid4()}", headers=h["admin"]).status_code == 404
