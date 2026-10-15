"""Stance suggestions: how an item bears on an event, suggested with its reason, decided
by the analyst, logged with whether it was followed, and never shown to second-opinion
annotators."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.event import EvidenceJudgement, EvidenceRelation
from app.models.field_report import FieldReport
from app.services import stance
from app.services.audit import AuditAction
from tests.test_assessment import NOW, _event, _report
from tests.test_assessment import people as people  # noqa: F401 (fixture)

THREE_DEAD = "Mirpur 10 e pani, 3 jon mara geche"
TWENTY_DEAD = "Mirpur 10 e pani, 20 jon mara geche"


def _stance(client, people, event, text, event_type=None) -> dict:
    r = client.post(
        f"/api/v1/events/{event.id}/stance",
        json={"text": text, "event_type": event_type},
        headers=people["analyst_headers"],
    )
    assert r.status_code == 200, r.text
    return r.json()


def _unlinked_report(db, worker, text) -> FieldReport:
    r = FieldReport(
        id=uuid.uuid4(),
        client_report_id=uuid.uuid4(),
        reporter_id=worker.id,
        text=text,
        event_type="waterlogging",
        latitude=23.8069,
        longitude=90.3687,
        observed_at=NOW,
        received_at=NOW + timedelta(minutes=5),
        content_hash="1" * 64,
    )
    db.add(r)
    db.flush()
    return r


# --- The rules -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "event_type", "relation", "strength", "reason"),
    [
        ("Mirpur 10 e pani jomeche, eta gujob", None, "contradicts", "strong", "calls it false"),
        ("The report of waterlogging in Mirpur is false", None, "contradicts", "strong", "false"),
        ("Fire at a garment factory in Mirpur, firefighters on scene", None, "unrelated",
         "medium", "about a fire, not a waterlogging"),
        ("Water everywhere", "fire", "unrelated", "medium", "about a fire"),
        ("Mirpur e ki hoise? keu janen?", None, "related", "weak", "asks or comments"),
        ("মিরপুরে কী হয়েছে? সবাই দোয়া করবেন", None, "related", "weak", "asks or comments"),
        ("Knee-deep water on Mirpur 10 road this morning", None, "supports", "weak",
         "nothing in it says otherwise"),
        ("Water everywhere", "waterlogging", "supports", "weak", "reports a waterlogging"),
    ],
)  # fmt: skip
def test_rules(client, db, people, text, event_type, relation, strength, reason):
    e = _event(db, people["analyst"])
    db.commit()
    s = _stance(client, people, e, text, event_type)
    assert (s["relation"], s["strength"]) == (relation, strength)
    assert reason in " ".join(s["reasons"]) and s["conflicts"] == []


def test_a_detail_against_credible_sources_is_partial(client, db, people):
    a, (w1, w2, _) = people["analyst"], people["workers"]
    e = _event(db, a)
    db.commit()
    s = _stance(client, people, e, TWENTY_DEAD)
    assert s["relation"] == "supports"  # nothing to compare with yet
    _report(db, e, w1, a, text=THREE_DEAD)
    _report(db, e, w2, a, text=THREE_DEAD, minutes=5)
    db.commit()
    s = _stance(client, people, e, TWENTY_DEAD)
    assert (s["relation"], s["conflicts"]) == ("partially_supports", ["casualty_count"])
    assert s["reasons"] == ["says 20 dead; other sources say 3 dead"]
    assert _stance(client, people, e, THREE_DEAD)["relation"] == "supports"


def test_the_endpoint_checks_its_input(client, db, people):
    e = _event(db, people["analyst"])
    db.commit()
    h = people["analyst_headers"]
    assert (
        client.post(f"/api/v1/events/{e.id}/stance", json={"text": "x"}, headers=h).status_code
        == 422
    )
    missing = client.post(
        f"/api/v1/events/{uuid.uuid4()}/stance", json={"text": "water"}, headers=h
    )
    assert missing.status_code == 404


# --- In the product --------------------------------------------------------------------------


def test_each_linked_item_is_read_without_itself(client, db, people):
    a, (w1, w2, w3) = people["analyst"], people["workers"]
    e = _event(db, a)
    _report(db, e, w1, a, text=THREE_DEAD)
    _report(db, e, w2, a, text=THREE_DEAD, minutes=5)
    _report(db, e, w3, a, text=TWENTY_DEAD, minutes=10)
    db.commit()
    items = client.get(f"/api/v1/events/{e.id}/evidence", headers=people["analyst_headers"]).json()
    by_text = {i["field_report"]["text"]: i["stance"] for i in items}
    assert by_text[TWENTY_DEAD]["relation"] == "partially_supports"
    # Each "3 dead" report is compared with the other two, which disagree with each other.
    assert all(i["stance"] is not None for i in items)


def test_candidates_carry_a_stance(client, db, people):
    a, (w1, _, _) = people["analyst"], people["workers"]
    e = _event(db, a)
    _unlinked_report(db, w1, "Mirpur 10 e pani jomeche, eta gujob")
    db.commit()
    got = client.get(
        f"/api/v1/events/{e.id}/candidate-reports", headers=people["analyst_headers"]
    ).json()
    assert got and got[0]["stance"]["relation"] == "contradicts"
    report_id = got[0]["report"]["id"]
    events = client.get(
        f"/api/v1/field-reports/{report_id}/candidate-events", headers=people["analyst_headers"]
    ).json()
    assert events and events[0]["stance"]["relation"] == "contradicts"


def test_the_audit_log_says_whether_it_was_followed(client, db, people):
    a, (w1, _, _) = people["analyst"], people["workers"]
    e = _event(db, a)
    r = _unlinked_report(db, w1, "Mirpur 10 e pani jomeche, eta gujob")
    db.commit()
    h = people["analyst_headers"]
    body = {"field_report_id": str(r.id), "relation": "supports", "conflicts": []}
    link = client.post(f"/api/v1/events/{e.id}/evidence", json=body, headers=h)
    assert link.status_code == 201, link.text
    changed = client.patch(
        f"/api/v1/events/{e.id}/evidence/{link.json()['id']}",
        json={"relation": "contradicts", "conflicts": []},
        headers=h,
    )
    assert changed.status_code == 200, changed.text
    logged = {
        row.action: row.details["stance_suggested"]
        for row in db.scalars(select(AuditLog).where(AuditLog.target_id == str(e.id))).all()
        if row.details and "stance_suggested" in row.details
    }
    assert logged[AuditAction.EVIDENCE_LINKED] == {
        "relation": "contradicts", "strength": "strong", "followed": False,
    }  # fmt: skip
    assert logged[AuditAction.EVIDENCE_UPDATED]["followed"] is True

    result = stance.evaluate(db)
    assert result["followed"] == {"shown": 2, "followed": 1}
    assert result["working_labels"]["accuracy"] == 1.0  # now labelled contradicts
    assert "followed 1" in stance.table(result)


def test_evaluation_against_blind_second_opinions(db, people):
    a, (w1, w2, _) = people["analyst"], people["workers"]
    e = _event(db, a)
    links = [
        _report(
            db,
            e,
            w1,
            a,
            text="Mirpur 10 e pani jomeche, eta gujob",
            relation=EvidenceRelation.CONTRADICTS,
        ),
        _report(db, e, w2, a, text="Knee-deep water on Mirpur 10 road", minutes=5),
    ]
    db.flush()
    for link, label in zip(links, ("contradicts", "related"), strict=True):
        db.add(
            EvidenceJudgement(
                evidence_id=link.id,
                annotator_id=w1.id,
                relation=EvidenceRelation(label),
                blind=True,
            )
        )
    db.commit()
    db.expire_all()
    r = stance.evaluate(db)["blind_second_opinions"]
    assert r["n"] == 2 and r["accuracy"] == 0.5
    assert r["confusion"]["related"]["supports"] == 1
    assert r["per_relation"]["contradicts"]["f1"] == 1.0


def test_second_opinion_annotators_never_see_a_suggestion(client, db, people, make_user, login):
    a, (w1, _, _) = people["analyst"], people["workers"]
    e = _event(db, a)
    _report(db, e, w1, a, text="Mirpur 10 e pani jomeche, eta gujob")
    db.commit()
    make_user("second@office.local", people["analyst"].role)
    queue = client.get("/api/v1/annotation/queue", headers=login("second@office.local")).json()
    assert queue["total"] == 1
    assert "stance" not in str(queue) and "calls it false" not in str(queue)
