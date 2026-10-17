"""The review queue (open events, the ones where a check matters most first) and
requests for more evidence answered by field reports."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.event_types import EVENT_TYPE_FAMILY
from app.models.audit import AuditLog
from app.models.event import Event, EventEvidence, EventStatus, EvidenceRelation, Priority
from app.models.field_report import FieldReport
from app.models.user import Role
from app.services import assess, triage
from tests.test_field_reports import submit

NOW = datetime.now(UTC).replace(microsecond=0)
S, C = EvidenceRelation.SUPPORTS, EvidenceRelation.CONTRADICTS
QUEUE = "/api/v1/review-queue"


def _v(key, vote=1, kind="field"):
    return assess.Vote(key, kind, key, vote, S if vote > 0 else C, (), NOW)


# --- The value of a check, without a database ---------------------------------------------------


def test_no_evidence_always_changes():
    v = triage.check_value(assess.STARTING, [])
    assert v.probability is None and v.changes == 1.0 and v.uncertainty == 1.0
    assert v.if_supported == pytest.approx(0.8) and v.if_denied == pytest.approx(0.2)


def test_one_supporting_report_can_still_be_overturned():
    # One worker (80 %): a second saying yes keeps it verified; one saying no makes it
    # 50 %, open. So a check changes it only if the answer is no.
    v = triage.check_value(assess.STARTING, [_v("a")])
    assert v.probability == pytest.approx(0.8)
    assert v.if_supported > 0.9 and v.if_denied == pytest.approx(0.5)
    chance_no = 1 - (0.8 * 0.8 + 0.2 * 0.2)
    assert v.changes == pytest.approx(chance_no)
    assert v.uncertainty == pytest.approx(0.4)


def test_a_settled_event_needs_no_check():
    vs = [_v(k) for k in "abcd"]
    v = triage.check_value(assess.STARTING, vs)
    assert v.probability > 0.99 and v.changes == 0.0


def test_a_conflict_is_decided_by_the_next_report():
    v = triage.check_value(assess.STARTING, [_v("a"), _v("b", -1)])
    assert v.probability == pytest.approx(0.5)
    assert v.changes == pytest.approx(1.0) and v.uncertainty == pytest.approx(1.0)


# --- The queue through the API --------------------------------------------------------------------


@pytest.fixture
def people(make_user, login):
    analyst = make_user("analyst@office.local", Role.ANALYST)
    workers = [make_user(f"worker{k}@office.local", Role.FIELD_WORKER) for k in range(4)]
    return {
        "analyst": analyst,
        "workers": workers,
        "analyst_headers": login("analyst@office.local"),
        "worker_headers": login("worker0@office.local"),
    }


def _event(db, analyst, title, priority=Priority.MEDIUM, status=EventStatus.ACTIVE, hours=6):
    e = Event(
        id=uuid.uuid4(),
        title=title,
        event_type="waterlogging",
        family=EVENT_TYPE_FAMILY["waterlogging"],
        place_name="Mirpur 10",
        latitude=23.8069,
        longitude=90.3687,
        started_at=NOW - timedelta(hours=hours),
        created_by_id=analyst.id,
        priority=priority,
        status=status,
    )
    db.add(e)
    db.flush()
    return e


def _link(db, event, worker, analyst, relation=S):
    r = FieldReport(
        id=uuid.uuid4(), client_report_id=uuid.uuid4(), reporter_id=worker.id,
        text="water at mirpur 10", event_type="waterlogging", latitude=23.8069,
        longitude=90.3687, observed_at=NOW, received_at=NOW, content_hash="0" * 64,
    )  # fmt: skip
    db.add(r)
    db.flush()
    db.add(
        EventEvidence(
            id=uuid.uuid4(),
            event_id=event.id,
            field_report_id=r.id,
            relation=relation,
            linked_by_id=analyst.id,
        )  # fmt: skip
    )
    db.flush()


def test_queue_orders_by_impact_and_need(client, db, people):
    a, w = people["analyst"], people["workers"]
    settled = _event(db, a, "Settled", Priority.CRITICAL)
    for k in range(4):
        _link(db, settled, w[k], a)
    conflict = _event(db, a, "Conflicting", Priority.HIGH)
    _link(db, conflict, w[0], a)
    _link(db, conflict, w[1], a, C)
    empty_low = _event(db, a, "Nothing yet, low", Priority.LOW)
    empty_med = _event(db, a, "Nothing yet, medium", Priority.MEDIUM)
    _event(db, a, "Over", Priority.CRITICAL, status=EventStatus.RESOLVED)
    db.commit()

    r = client.get(QUEUE, headers=people["analyst_headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 4  # the resolved event is not in the queue
    titles = [i["event"]["title"] for i in body["items"]]
    # High x fully uncertain (3.0) > medium, no evidence (2.0) > low, no evidence (1.0)
    # > critical but settled (4 x ~0).
    assert titles == ["Conflicting", "Nothing yet, medium", "Nothing yet, low", "Settled"]
    top = body["items"][0]
    assert top["score"] == pytest.approx(3.0) and top["impact"] == 3
    assert any("Either answer would change" in x for x in top["reasons"])
    assert any("differs from the suggested one" in x for x in top["reasons"])  # unverified
    assert top["differs"] is True and top["suggested"] == "conflicting"
    assert {empty_low.id, empty_med.id} <= {uuid.UUID(i["event"]["id"]) for i in body["items"]}
    # A new event (unverified) with no evidence (insufficient evidence) is not a disagreement.
    empty = next(i for i in body["items"] if i["event"]["title"] == "Nothing yet, low")
    assert empty["differs"] is False


def test_queue_is_for_analysts(client, people):
    assert client.get(QUEUE, headers=people["worker_headers"]).status_code == 403


# --- Requests for more evidence ---------------------------------------------------------------


QUESTION = "Is there waterlogging at Mirpur 10 now? Say what you see, even if nothing is."


def _request(client, people, event, question=QUESTION):
    return client.post(
        f"/api/v1/events/{event.id}/evidence-requests",
        json={"question": question},
        headers=people["analyst_headers"],
    )


def test_request_answer_and_close(client, db, people):
    event = _event(db, people["analyst"], "Waterlogging at Mirpur 10", Priority.HIGH)
    db.commit()
    r = _request(client, people, event)
    assert r.status_code == 201, r.text
    request_id = r.json()["id"]
    assert _request(client, people, event).status_code == 409  # one open at a time

    # Field workers see what to check and where, nothing about what is believed.
    seen = client.get("/api/v1/evidence-requests/open", headers=people["worker_headers"]).json()
    assert len(seen) == 1 and seen[0]["question"] == QUESTION
    assert seen[0]["place_name"] == "Mirpur 10" and seen[0]["answered_by_me"] == 0
    assert not {"assessment", "probability", "title", "priority"} & set(seen[0])

    # Answer it with a report; the report says which request it answers.
    sent = submit(client, people["worker_headers"], request_id=request_id)
    assert sent.status_code == 201, sent.text
    report = sent.json()
    assert report["request"]["id"] == request_id and report["request"]["question"] == QUESTION
    # Its content hash covers the request, and still verifies.
    check = client.get(
        f"/api/v1/field-reports/{report['id']}/verify", headers=people["analyst_headers"]
    ).json()
    assert check["intact"] is True
    seen = client.get("/api/v1/evidence-requests/open", headers=people["worker_headers"]).json()
    assert seen[0]["answered_by_me"] == 1

    listed = client.get(
        f"/api/v1/events/{event.id}/evidence-requests", headers=people["analyst_headers"]
    ).json()
    assert [x["id"] for x in listed[0]["responses"]] == [report["id"]]
    # An answer is a candidate for the event even from far away.
    far = submit(client, people["worker_headers"], request_id=request_id, latitude=22.3569,
                 longitude=91.7832).json()  # fmt: skip
    candidates = client.get(
        f"/api/v1/events/{event.id}/candidate-reports", headers=people["analyst_headers"]
    ).json()
    ids = [c["report"]["id"] for c in candidates]
    assert far["id"] in ids and report["id"] in ids
    item = client.get(f"{QUEUE}/{event.id}", headers=people["analyst_headers"]).json()
    assert item["open_request"]["responses"] == 2
    assert "A check was requested; 2 answers so far." in item["reasons"]

    closed = client.post(
        f"/api/v1/evidence-requests/{request_id}/close",
        json={"status": "answered", "note": "Two workers went"},
        headers=people["analyst_headers"],
    )
    assert closed.status_code == 200 and closed.json()["status"] == "answered"
    again = client.post(
        f"/api/v1/evidence-requests/{request_id}/close",
        json={"status": "cancelled"},
        headers=people["analyst_headers"],
    )
    assert again.status_code == 409
    # A closed request cannot be answered any more, and is no longer shown.
    late = submit(client, people["worker_headers"], request_id=request_id)
    assert late.status_code == 422 and "closed" in late.json()["detail"]
    assert (
        client.get("/api/v1/evidence-requests/open", headers=people["worker_headers"]).json() == []
    )
    actions = db.scalars(select(AuditLog.action)).all()
    assert "event.evidence_requested" in actions and "event.evidence_request_closed" in actions


def test_only_analysts_ask_and_only_open_events(client, db, people):
    event = _event(db, people["analyst"], "Over", status=EventStatus.RESOLVED)
    db.commit()
    assert _request(client, people, event).status_code == 409
    worker = client.post(
        f"/api/v1/events/{event.id}/evidence-requests",
        json={"question": QUESTION},
        headers=people["worker_headers"],
    )
    assert worker.status_code == 403
    assert _request(client, people, event, question="short").status_code == 422


def test_resolving_the_event_cancels_its_request(client, db, people):
    event = _event(db, people["analyst"], "Waterlogging at Mirpur 10")
    db.commit()
    request_id = _request(client, people, event).json()["id"]
    r = client.patch(
        f"/api/v1/events/{event.id}", json={"status": "resolved"},
        headers=people["analyst_headers"],
    )  # fmt: skip
    assert r.status_code == 200, r.text
    listed = client.get(
        f"/api/v1/events/{event.id}/evidence-requests", headers=people["analyst_headers"]
    ).json()
    assert listed[0]["id"] == request_id and listed[0]["status"] == "cancelled"
    assert "resolved" in listed[0]["close_note"]


def test_unknown_request_is_refused(client, people):
    r = submit(client, people["worker_headers"], request_id=str(uuid.uuid4()))
    assert r.status_code == 422
