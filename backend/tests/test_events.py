from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.field_report import FieldReport, ReportStatus
from app.models.user import Role
from app.services.audit import AuditAction
from tests.test_field_reports import DHAKA, MIRPUR, photo, submit

URL = "/api/v1/events"
NOW = datetime.now(DHAKA).replace(microsecond=0)
# About 30 km north of Mirpur: well outside the 5 km matching radius.
GAZIPUR = (24.0023, 90.4264)


@pytest.fixture
def worker(make_user, login):
    make_user("worker@office.local", Role.FIELD_WORKER)
    return login("worker@office.local")


@pytest.fixture
def worker2(make_user, login):
    make_user("worker2@office.local", Role.FIELD_WORKER)
    return login("worker2@office.local")


@pytest.fixture
def analyst(make_user, login):
    make_user("analyst@office.local", Role.ANALYST, full_name="Ana Analyst")
    return login("analyst@office.local")


@pytest.fixture
def viewer(make_user, login):
    make_user("viewer@office.local", Role.VIEWER)
    return login("viewer@office.local")


def event_body(**overrides) -> dict:
    body = {
        "title": "Waterlogging at Mirpur 10 circle",
        "event_type": "waterlogging",
        "place_name": "Mirpur 10 golchottor",
        "latitude": MIRPUR[0],
        "longitude": MIRPUR[1],
        "started_at": (NOW - timedelta(hours=2)).isoformat(),
    }
    body.update(overrides)
    return {k: v for k, v in body.items() if v is not None}


def create(client, headers, **overrides):
    return client.post(URL, json=event_body(**overrides), headers=headers)


def report(client, headers, **overrides) -> dict:
    response = submit(client, headers, **overrides)
    assert response.status_code == 201, response.text
    return response.json()


# --- Creating and reading --------------------------------------------------------------


def test_analyst_creates_event_with_defaults(client, analyst, db):
    response = create(client, analyst)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["family"] == "natural_calamity"
    assert (body["status"], body["priority"], body["assessment"]) == (
        "active",
        "medium",
        "unverified",
    )
    assert body["created_by"]["full_name"] == "Ana Analyst"
    assert body["evidence_counts"] == {
        "supports": 0,
        "partially_supports": 0,
        "contradicts": 0,
        "related": 0,
        "reporters": 0,
        "photos": 0,
    }
    entry = db.scalar(select(AuditLog).where(AuditLog.action == AuditAction.EVENT_CREATED))
    assert entry.target_id == body["id"]


def test_create_from_reports_links_them_as_support(client, analyst, worker, worker2, db):
    r1 = report(client, worker, photos=[photo(1)])
    r2 = report(client, worker2, photos=[photo(2), photo(3)])

    response = create(client, analyst, field_report_ids=[r1["id"], r2["id"], r1["id"]])

    assert response.status_code == 201, response.text
    counts = response.json()["evidence_counts"]
    assert counts["supports"] == 2  # duplicate id ignored
    assert counts["reporters"] == 2
    assert counts["photos"] == 3
    # Placing a report against an event marks it reviewed.
    statuses = db.scalars(select(FieldReport.status)).all()
    assert set(statuses) == {ReportStatus.REVIEWED}


def test_create_with_unknown_report_creates_nothing(client, analyst):
    missing = "00000000-0000-4000-8000-000000000000"
    response = create(client, analyst, field_report_ids=[missing])

    assert response.status_code == 422
    assert missing in response.json()["detail"]
    assert client.get(URL, headers=analyst).json()["total"] == 0


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"event_type": "political_rally"}, "Unknown event_type"),
        ({"title": "   ab   "}, "at least 5 characters"),
        ({"latitude": 27.5}, "less than or equal to 26.7"),
        ({"started_at": "2026-10-03T10:00:00"}, "UTC offset"),
        (
            {"ended_at": (NOW - timedelta(hours=5)).isoformat()},
            "ended_at must not be before started_at",
        ),
    ],
)
def test_create_validation(client, analyst, overrides, message):
    response = create(client, analyst, **overrides)

    assert response.status_code == 422
    assert message in response.text


@pytest.mark.parametrize("who", ["worker", "viewer"])
def test_only_reviewers_create_events(client, request, who):
    assert create(client, request.getfixturevalue(who)).status_code == 403


def test_everyone_signed_in_can_read_events(client, analyst, worker, viewer):
    event = create(client, analyst).json()

    for headers in (worker, viewer):
        assert client.get(URL, headers=headers).json()["total"] == 1
        assert client.get(f"{URL}/{event['id']}", headers=headers).status_code == 200
    assert client.get(URL).status_code == 401


def test_list_filters_and_order(client, analyst):
    old = create(client, analyst, started_at=(NOW - timedelta(days=2)).isoformat()).json()
    new = create(client, analyst, title="Fire at Karwan Bazar market", event_type="fire").json()
    client.patch(f"{URL}/{old['id']}", json={"status": "resolved"}, headers=analyst)

    everything = client.get(URL, headers=analyst).json()
    assert [e["id"] for e in everything["items"]] == [new["id"], old["id"]]  # newest first

    active = client.get(URL, params={"status": "active"}, headers=analyst).json()
    assert [e["id"] for e in active["items"]] == [new["id"]]

    both = client.get(URL, params=[("status", "active"), ("status", "resolved")], headers=analyst)
    assert both.json()["total"] == 2

    urban = client.get(URL, params={"family": "urban_emergency"}, headers=analyst).json()
    assert [e["id"] for e in urban["items"]] == [new["id"]]

    assert client.get(URL, params={"family": "politics"}, headers=analyst).status_code == 422


def test_unknown_event_is_404(client, analyst):
    response = client.get(f"{URL}/00000000-0000-4000-8000-000000000000", headers=analyst)
    assert response.status_code == 404


# --- Updating --------------------------------------------------------------------------


def test_update_records_exactly_what_changed(client, analyst, db):
    event = create(client, analyst).json()

    response = client.patch(
        f"{URL}/{event['id']}",
        json={
            "assessment": "verified",
            "priority": "high",
            "title": "Waterlogging at Mirpur 10 circle",  # unchanged
            "event_type": "flood",
        },
        headers=analyst,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["assessment"], body["priority"], body["family"]) == (
        "verified",
        "high",
        "natural_calamity",
    )
    entry = db.scalar(select(AuditLog).where(AuditLog.action == AuditAction.EVENT_UPDATED))
    assert entry.details["changes"] == {
        "assessment": ["unverified", "verified"],
        "priority": ["medium", "high"],
        "event_type": ["waterlogging", "flood"],
    }


def test_update_changing_type_updates_family(client, analyst):
    event = create(client, analyst).json()
    body = client.patch(
        f"{URL}/{event['id']}", json={"event_type": "road_blockage"}, headers=analyst
    ).json()
    assert body["family"] == "road_infrastructure"


def test_update_without_changes_writes_no_audit_entry(client, analyst, db):
    event = create(client, analyst).json()
    client.patch(f"{URL}/{event['id']}", json={"status": "active"}, headers=analyst)

    assert db.scalar(select(AuditLog).where(AuditLog.action == AuditAction.EVENT_UPDATED)) is None


def test_resolve_with_end_time_and_clear_it_again(client, analyst):
    event = create(client, analyst).json()
    ended = NOW.isoformat()

    resolved = client.patch(
        f"{URL}/{event['id']}", json={"status": "resolved", "ended_at": ended}, headers=analyst
    ).json()
    assert resolved["ended_at"] is not None

    reopened = client.patch(
        f"{URL}/{event['id']}", json={"status": "active", "ended_at": None}, headers=analyst
    ).json()
    assert reopened["ended_at"] is None


def test_update_rejects_end_before_start_and_null_required_fields(client, analyst):
    event = create(client, analyst).json()
    early = (NOW - timedelta(days=1)).isoformat()

    assert (
        client.patch(f"{URL}/{event['id']}", json={"ended_at": early}, headers=analyst).status_code
        == 422
    )
    response = client.patch(f"{URL}/{event['id']}", json={"title": None}, headers=analyst)
    assert response.status_code == 422
    assert "title cannot be empty" in response.text


def test_only_reviewers_update(client, analyst, worker):
    event = create(client, analyst).json()
    response = client.patch(f"{URL}/{event['id']}", json={"status": "resolved"}, headers=worker)
    assert response.status_code == 403


# --- Evidence --------------------------------------------------------------------------


def test_link_change_and_unlink_evidence(client, analyst, worker, db):
    event = create(client, analyst).json()
    r = report(client, worker, photos=[photo(1)])
    evidence_url = f"{URL}/{event['id']}/evidence"

    linked = client.post(
        evidence_url,
        json={"field_report_id": r["id"], "relation": "contradicts", "note": "  Says dry.  "},
        headers=analyst,
    )
    assert linked.status_code == 201, linked.text
    item = linked.json()
    assert item["note"] == "Says dry."
    assert item["field_report"]["id"] == r["id"]
    assert item["linked_by"]["full_name"] == "Ana Analyst"
    counts = client.get(f"{URL}/{event['id']}", headers=analyst).json()["evidence_counts"]
    assert (counts["contradicts"], counts["photos"]) == (1, 1)

    again = client.post(
        evidence_url, json={"field_report_id": r["id"], "relation": "supports"}, headers=analyst
    )
    assert again.status_code == 409

    changed = client.patch(
        f"{evidence_url}/{item['id']}", json={"relation": "supports"}, headers=analyst
    )
    assert changed.json()["relation"] == "supports"

    assert client.delete(f"{evidence_url}/{item['id']}", headers=analyst).status_code == 204
    assert client.get(evidence_url, headers=analyst).json() == []

    actions = db.scalars(
        select(AuditLog.action).where(AuditLog.target_id == event["id"]).order_by(AuditLog.id)
    ).all()
    assert actions == [
        AuditAction.EVENT_CREATED,
        AuditAction.EVIDENCE_LINKED,
        AuditAction.EVIDENCE_UPDATED,
        AuditAction.EVIDENCE_UNLINKED,
    ]


def test_link_unknown_report(client, analyst):
    event = create(client, analyst).json()
    response = client.post(
        f"{URL}/{event['id']}/evidence",
        json={"field_report_id": "00000000-0000-4000-8000-000000000000", "relation": "supports"},
        headers=analyst,
    )
    assert response.status_code == 422


def test_evidence_of_another_event_is_404(client, analyst, worker):
    a = create(client, analyst).json()
    b = create(client, analyst, title="Another waterlogging spot").json()
    r = report(client, worker)
    item = client.post(
        f"{URL}/{a['id']}/evidence",
        json={"field_report_id": r["id"], "relation": "supports"},
        headers=analyst,
    ).json()

    response = client.delete(f"{URL}/{b['id']}/evidence/{item['id']}", headers=analyst)
    assert response.status_code == 404


def test_evidence_is_for_reviewers_only(client, analyst, worker, viewer):
    event = create(client, analyst).json()
    for headers in (worker, viewer):
        assert client.get(f"{URL}/{event['id']}/evidence", headers=headers).status_code == 403
        assert client.get(f"{URL}/{event['id']}/history", headers=headers).status_code == 403


def test_history_shows_actor_and_changes(client, analyst):
    event = create(client, analyst).json()
    client.patch(f"{URL}/{event['id']}", json={"assessment": "verified"}, headers=analyst)

    entries = client.get(f"{URL}/{event['id']}/history", headers=analyst).json()

    assert [e["action"] for e in entries] == ["event.created", "event.updated"]
    assert entries[1]["actor"]["full_name"] == "Ana Analyst"
    assert entries[1]["details"]["changes"]["assessment"] == ["unverified", "verified"]


def test_report_events_lists_links(client, analyst, worker):
    r = report(client, worker)
    event = create(client, analyst, field_report_ids=[r["id"]]).json()

    links = client.get(f"/api/v1/field-reports/{r['id']}/events", headers=analyst).json()

    assert [(link["event"]["id"], link["relation"]) for link in links] == [
        (event["id"], "supports")
    ]
    assert client.get(f"/api/v1/field-reports/{r['id']}/events", headers=worker).status_code == 403


# --- Matching --------------------------------------------------------------------------


def test_candidate_reports_near_in_space_and_time(client, analyst, worker, worker2):
    event = create(client, analyst).json()
    near = report(client, worker, place_name="Mirpur 10")
    near_other_type = report(
        client,
        worker2,
        event_type="road_blockage",
        latitude=MIRPUR[0] + 0.01,  # ~1.1 km north
    )
    report(client, worker2, latitude=GAZIPUR[0], longitude=GAZIPUR[1])  # too far
    report(client, worker, observed_at=(NOW - timedelta(days=4)).isoformat())  # too long before

    candidates = client.get(f"{URL}/{event['id']}/candidate-reports", headers=analyst).json()

    assert [c["report"]["id"] for c in candidates] == [near["id"], near_other_type["id"]]
    assert candidates[0]["same_type"] is True
    assert candidates[0]["distance_km"] < 0.1
    assert candidates[0]["hours_apart"] == 0
    assert 1.0 < candidates[1]["distance_km"] < 1.3

    # Once linked, a report is no longer suggested.
    client.post(
        f"{URL}/{event['id']}/evidence",
        json={"field_report_id": near["id"], "relation": "supports"},
        headers=analyst,
    )
    again = client.get(f"{URL}/{event['id']}/candidate-reports", headers=analyst).json()
    assert [c["report"]["id"] for c in again] == [near_other_type["id"]]


def test_candidate_events_for_a_report(client, analyst, worker):
    same = create(client, analyst).json()
    other_type = create(
        client, analyst, title="Road blocked at Mirpur 10", event_type="road_blockage"
    ).json()
    create(
        client, analyst, title="Far away waterlogging", latitude=GAZIPUR[0], longitude=GAZIPUR[1]
    )
    dismissed = create(client, analyst, title="Mistaken waterlogging").json()
    client.patch(f"{URL}/{dismissed['id']}", json={"status": "dismissed"}, headers=analyst)
    ended_long_ago = create(
        client,
        analyst,
        title="Old waterlogging episode",
        started_at=(NOW - timedelta(days=10)).isoformat(),
        ended_at=(NOW - timedelta(days=9)).isoformat(),
    ).json()
    r = report(client, worker)

    candidates = client.get(
        f"/api/v1/field-reports/{r['id']}/candidate-events", headers=analyst
    ).json()

    ids = [c["event"]["id"] for c in candidates]
    assert ids == [same["id"], other_type["id"]]
    assert ended_long_ago["id"] not in ids
    assert candidates[0]["same_type"] is True
    assert candidates[1]["same_type"] is False
    assert candidates[1]["same_family"] is False


def test_open_event_matches_reports_until_now(client, analyst, worker):
    started_last_week = (datetime.now(UTC) - timedelta(days=7)).isoformat()
    event = create(client, analyst, started_at=started_last_week).json()
    r = report(client, worker)

    candidates = client.get(
        f"/api/v1/field-reports/{r['id']}/candidate-events", headers=analyst
    ).json()

    assert [c["event"]["id"] for c in candidates] == [event["id"]]
    assert candidates[0]["hours_apart"] == 0


def test_list_search_and_priority_filter(client, analyst):
    fire = create(
        client,
        analyst,
        title="Fire at Karwan Bazar market",
        event_type="fire",
        place_name="Karwan Bazar",
        priority="critical",
    ).json()
    mirpur = create(client, analyst, priority="high").json()  # "Mirpur" in title and place
    create(
        client,
        analyst,
        title="Flood near 100% submerged_area",
        event_type="flood",
        place_name="Sylhet",
        summary="Roads under Mirpur-style water",
    )

    def ids(**params):
        return [e["id"] for e in client.get(URL, params=params, headers=analyst).json()["items"]]

    assert ids(q="karwan") == [fire["id"]]
    assert set(ids(q="MIRPUR 10")) == {mirpur["id"]}
    assert len(ids(q="mirpur")) == 2  # the summary matches too
    assert len(ids(q="100%")) == 1  # LIKE wildcards are literal
    assert len(ids(q="_")) == 1
    assert ids(priority="critical") == [fire["id"]]
    both = client.get(URL, params=[("priority", "critical"), ("priority", "high")], headers=analyst)
    assert both.json()["total"] == 2
    assert client.get(URL, params={"priority": "urgent"}, headers=analyst).status_code == 422
