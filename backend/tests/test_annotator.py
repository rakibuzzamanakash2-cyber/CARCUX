"""Annotator accounts: blind second opinions, enforced by the server. An annotator can
read the queue and give judgements; every other signed-in route refuses them, and the
queue carries nothing that reveals another judgement or CARCUX's reading."""

import uuid

import pytest
from sqlalchemy import select

from app.models.event import EventEvidence, EvidenceJudgement, EvidenceRelation
from app.models.user import Role
from tests.conftest import PASSWORD
from tests.test_assessment import _event, _feed, _report, _signal
from tests.test_assessment import people as people  # noqa: F401 (fixture)

ANNOTATOR = "annotator.b@carcux.org"


@pytest.fixture
def pilot(db, people, make_user, login):
    """One event with a field report and a signal, each with the analyst's first label."""
    a, (w1, _, _) = people["analyst"], people["workers"]
    e = _event(db, a)
    report = _report(
        db, e, w1, a, relation=EvidenceRelation.CONTRADICTS, text="Mirpur 10 e pani, eta gujob"
    )
    _signal(db, e, _feed(db), a)
    db.flush()
    for link in db.scalars(select(EventEvidence).where(EventEvidence.event_id == e.id)):
        db.add(EvidenceJudgement(evidence_id=link.id, annotator_id=a.id, relation=link.relation))
    db.commit()
    make_user(ANNOTATOR, Role.ANNOTATOR, full_name="Annotator B")
    return {"event": e, "report_link": report, "headers": login(ANNOTATOR)}


def test_an_annotator_can_judge_the_queue(client, db, pilot):
    h = pilot["headers"]
    assert client.get("/api/v1/auth/me", headers=h).json()["role"] == "annotator"
    queue = client.get("/api/v1/annotation/queue", headers=h)
    assert queue.status_code == 200, queue.text
    assert queue.json()["total"] == 2
    r = client.post(
        "/api/v1/annotation/judgements",
        json={"evidence_id": str(pilot["report_link"].id), "relation": "contradicts"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    assert client.get("/api/v1/annotation/queue", headers=h).json()["total"] == 1


def test_the_queue_reveals_no_other_judgement(client, pilot, people):
    body = client.get("/api/v1/annotation/queue", headers=pilot["headers"]).json()
    item = next(i for i in body["items"] if i["field_report"])
    assert set(item["event"]) == {
        "id", "title", "summary", "event_type", "family", "place_name", "latitude",
        "longitude", "started_at", "ended_at", "occurred", "ground_truth_sources",
        "ground_truth_note",
    }  # fmt: skip
    text = str(body)
    for leak in (
        "contradicts", "supports", "relation", "assessment", "evidence_counts",
        "extraction", "stance", "details", "reviewed_by", "review_note", "reporter",
        "created_by", "linked_by",
    ):  # fmt: skip
        assert leak not in text, leak
    # Analysts get the same blind queue.
    same = client.get("/api/v1/annotation/queue", headers=people["analyst_headers"]).json()
    assert "evidence_counts" not in str(same)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/events"),
        ("GET", "/events/{event}"),
        ("GET", "/events/{event}/evidence"),
        ("POST", "/events/{event}/stance"),
        ("GET", "/signals"),
        ("GET", "/field-reports"),
        ("GET", "/overview"),
        ("GET", "/annotation/agreement"),
        ("GET", "/annotation/disagreements"),
        ("GET", "/audit"),
        ("GET", "/dataset/summary"),
        ("GET", "/sources"),
        ("GET", "/users"),
        ("GET", "/official-pages"),
    ],
)
def test_everything_else_is_refused(client, pilot, method, path):
    url = "/api/v1" + path.format(event=pilot["event"].id)
    body = {"text": "water"} if method == "POST" else None
    r = client.request(method, url, json=body, headers=pilot["headers"])
    assert r.status_code == 403, (path, r.status_code, r.text[:200])


def test_an_annotator_can_change_their_password(client, pilot):
    r = client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": "another long password"},
        headers=pilot["headers"],
    )
    assert r.status_code == 200, r.text


def test_admins_create_annotators(client, admin_headers):
    r = client.post(
        "/api/v1/users",
        json={
            "email": "annotator.c@carcux.org",
            "full_name": "Annotator C",
            "password": "a long enough password",
            "role": "annotator",
        },
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "annotator"


def test_a_judgement_on_an_unknown_link_is_refused(client, pilot):
    r = client.post(
        "/api/v1/annotation/judgements",
        json={"evidence_id": str(uuid.uuid4()), "relation": "supports"},
        headers=pilot["headers"],
    )
    assert r.status_code == 422
