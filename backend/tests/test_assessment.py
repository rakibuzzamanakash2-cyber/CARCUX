"""Assessment suggestions: starting assumptions until a model is trained on events with
ground truth, then each source's own record; analysts decide, and the audit log says
whether they followed the suggestion."""

import math
import uuid
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from sqlalchemy import select

from app.core.event_types import EVENT_TYPE_FAMILY
from app.models.audit import AuditLog
from app.models.event import Assessment, Event, EventEvidence, EvidenceRelation
from app.models.field_report import FieldReport
from app.models.signal import Adapter, Signal, Source, SourceType
from app.models.user import Role, User
from app.services import assess, dataset
from app.services.audit import AuditAction

NOW = datetime.now(UTC).replace(microsecond=0)
S, P, C = (
    EvidenceRelation.SUPPORTS,
    EvidenceRelation.PARTIALLY_SUPPORTS,
    EvidenceRelation.CONTRADICTS,
)


# --- Pieces, without a database ----------------------------------------------------------------


def _v(key, kind="field", vote=1, relation=S, conflicts=(), minutes=0):
    return assess.Vote(
        key, kind, key, vote, relation, tuple(conflicts), NOW + timedelta(minutes=minutes)
    )


def test_starting_assumptions_read_as_log_odds():
    one = [_v("a")]
    assert assess.STARTING.probability(one) == pytest.approx(0.80)
    two = [_v("a"), _v("b")]
    assert assess.STARTING.probability(two) == pytest.approx(16 / 17)  # 0.8 * 0.8 / (… + 0.04)
    denied = [_v("a"), _v("b", kind="public_record", vote=-1, relation=C)]
    assert assess.STARTING.probability(denied) < 0.5  # an official denial outweighs one worker


@pytest.mark.parametrize(
    ("votes", "label"),
    [
        ([], Assessment.INSUFFICIENT_EVIDENCE),
        ([_v("a"), _v("b")], Assessment.VERIFIED),
        (
            [_v("a"), _v("b", relation=P, conflicts=["casualty_count"])],
            Assessment.PARTIALLY_VERIFIED,
        ),
        ([_v("a", vote=-1, relation=C), _v("b", vote=-1, relation=C)], Assessment.REFUTED),
        ([_v("a"), _v("b", vote=-1, relation=C)], Assessment.CONFLICTING),
        ([_v("a", kind="other")], Assessment.UNVERIFIED),
    ],
)
def test_labels(votes, label):
    p = assess.STARTING.probability(votes) if votes else None
    assert assess.label_for(p, votes, assess.STARTING)[0] == label


def test_an_unreliable_source_disputing_a_detail_is_not_a_dispute():
    w = assess.Weights(rates={"bad": 0.2})
    vs = [_v("a"), _v("b"), _v("c"), _v("bad", relation=P, conflicts=["cause"])]
    p = w.probability(vs)
    assert p >= assess.HIGH
    assert assess.label_for(p, vs, w) == (Assessment.VERIFIED, [])


def test_reliability_is_learned_from_outcomes_and_shrunk():
    resolved = []
    for k in range(10):
        happened = k % 2 == 0
        vs = [
            _v("careful", vote=1 if happened else -1, relation=S if happened else C),
            _v("credulous", kind="other"),  # always says it happened
        ]
        resolved.append((vs, happened))
    w = assess.learn_rates(resolved)
    assert w.rates["careful"] > 0.85 > 0.6 > w.rates["credulous"]
    assert w.rates["credulous"] > 0.4  # five right, five wrong, pulled towards its kind
    assert w.rate(_v("someone new", kind="other")) == (w.type_rates["other"], False)


def test_platt_learns_the_scale():
    rng = np.random.default_rng(0)
    s = rng.normal(0, 2, 3000)
    y = (rng.random(3000) < 1 / (1 + np.exp(-0.5 * s))).astype(int)
    cal = assess.fit_platt(s, y)
    assert cal["a"] == pytest.approx(0.5, abs=0.08) and abs(cal["b"]) < 0.15
    assert assess.fit_platt(s, np.ones(3000, dtype=int)) is None


def test_weights_round_trip_and_reject_old_formats():
    w = assess.Weights({"a": 0.9}, {"field": 0.8}, {"a": 1.2, "b": -0.1})
    assert assess.Weights.from_json(w.as_json()) == w
    with pytest.raises(ValueError):
        assess.Weights.from_json({"version": 0, "rates": {}, "type_rates": {}})


# --- In the product ----------------------------------------------------------------------------


@pytest.fixture
def people(make_user, login):
    analyst = make_user("analyst@office.local", Role.ANALYST)
    workers = [make_user(f"worker{k}@office.local", Role.FIELD_WORKER) for k in range(3)]
    make_user("admin@office.local", Role.ADMIN)
    return {
        "analyst": analyst,
        "workers": workers,
        "analyst_headers": login("analyst@office.local"),
        "admin_headers": login("admin@office.local"),
    }


def _event(db, analyst: User, title="Waterlogging at Mirpur 10", occurred=None, hours=0) -> Event:
    e = Event(
        id=uuid.uuid4(),
        title=title,
        event_type="waterlogging",
        family=EVENT_TYPE_FAMILY["waterlogging"],
        latitude=23.8069,
        longitude=90.3687,
        started_at=NOW - timedelta(hours=hours + 6),
        created_by_id=analyst.id,
        occurred=occurred,
    )
    db.add(e)
    db.flush()
    return e


def _report(db, event, worker, analyst, relation=S, conflicts=(), minutes=0, gold=None):
    r = FieldReport(
        id=uuid.uuid4(),
        client_report_id=uuid.uuid4(),
        reporter_id=worker.id,
        text="water at mirpur 10",
        event_type="waterlogging",
        latitude=23.8069,
        longitude=90.3687,
        observed_at=NOW,
        received_at=NOW + timedelta(minutes=minutes),
        content_hash="0" * 64,
    )
    db.add(r)
    db.flush()
    link = EventEvidence(
        id=uuid.uuid4(),
        event_id=event.id,
        field_report_id=r.id,
        relation=relation,
        conflicts=list(conflicts),
        linked_by_id=analyst.id,
        gold_relation=gold,
    )
    db.add(link)
    return link


def _feed(db, name="Rumour Daily", kind=SourceType.NEWS) -> Source:
    src = Source(
        id=uuid.uuid4(), key=name.lower().replace(" ", "-"), name=name, source_type=kind,
        adapter=Adapter.RSS,
    )  # fmt: skip
    db.add(src)
    db.flush()
    return src


def _signal(db, event, source, analyst, relation=S, minutes=0):
    s = Signal(
        id=uuid.uuid4(),
        source_id=source.id,
        external_id=str(uuid.uuid4()),
        title="Mirpur flooded",
        published_at=NOW + timedelta(minutes=minutes),
        content_hash="0" * 64,
    )
    db.add(s)
    db.flush()
    db.add(
        EventEvidence(
            id=uuid.uuid4(),
            event_id=event.id,
            signal_id=s.id,
            relation=relation,
            linked_by_id=analyst.id,
        )  # fmt: skip
    )


def _suggestion(client, people, event) -> dict:
    r = client.get(
        f"/api/v1/events/{event.id}/assessment-suggestion", headers=people["analyst_headers"]
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_suggestion_from_starting_assumptions(client, db, people):
    a, (w1, w2, _) = people["analyst"], people["workers"]
    e = _event(db, a)
    _report(db, e, w1, a)
    _report(db, e, w2, a, relation=P, conflicts=["affected_count"])
    db.commit()
    s = _suggestion(client, people, e)
    assert s["method"] == "start" and s["model_id"] is None
    assert s["label"] == "partially_verified" and s["disputed"] == ["affected_count"]
    assert s["probability"] == pytest.approx(16 / 17, abs=1e-6)
    assert s["sources_supporting"] == 2 and s["credible_supporting"] == 2
    assert {r["source"] for r in s["reasons"]} == {
        "Field worker " + w1.full_name, "Field worker " + w2.full_name
    }  # fmt: skip


def test_no_evidence_and_unknown_people(client, db, people):
    e = _event(db, people["analyst"])
    db.commit()
    s = _suggestion(client, people, e)
    assert s["label"] == "insufficient_evidence" and s["probability"] is None
    worker_headers = client.post(
        "/api/v1/auth/login",
        json={"email": "worker0@office.local", "password": "correct-horse-battery-staple"},
    ).json()
    r = client.get(
        f"/api/v1/events/{e.id}/assessment-suggestion",
        headers={"Authorization": f"Bearer {worker_headers['access_token']}"},
    )
    assert r.status_code == 403
    r = client.get(
        f"/api/v1/events/{uuid.uuid4()}/assessment-suggestion", headers=people["analyst_headers"]
    )
    assert r.status_code == 404


def test_a_source_is_one_voice_and_gold_labels_win(client, db, people):
    a, (w1, w2, _) = people["analyst"], people["workers"]
    e = _event(db, a)
    for k in range(3):
        _report(db, e, w1, a, minutes=k)  # the same worker three times
    _report(db, e, w2, a, relation=S, gold=C)  # adjudicated: it denies
    db.commit()
    s = _suggestion(client, people, e)
    assert s["sources_supporting"] == 1 and s["sources_denying"] == 1
    assert s["label"] == "conflicting"


def test_setting_an_assessment_logs_the_suggestion(client, db, people):
    a, (w1, w2, _) = people["analyst"], people["workers"]
    e = _event(db, a)
    _report(db, e, w1, a)
    _report(db, e, w2, a)
    db.commit()
    url = f"/api/v1/events/{e.id}"
    h = people["analyst_headers"]
    assert client.patch(url, json={"assessment": "verified"}, headers=h).status_code == 200
    assert client.patch(url, json={"priority": "high"}, headers=h).status_code == 200
    assert client.patch(url, json={"assessment": "conflicting"}, headers=h).status_code == 200
    logs = db.scalars(
        select(AuditLog.details)
        .where(AuditLog.action == AuditAction.EVENT_UPDATED)
        .order_by(AuditLog.occurred_at)
    ).all()
    assert [d.get("suggestion", {}).get("followed") for d in logs] == [True, None, False]
    first = logs[0]["suggestion"]
    assert first["label"] == "verified" and first["method"] == "start"
    status = client.get("/api/v1/assessment/model", headers=h).json()
    assert status["from_suggestions"] == {"total": 2, "followed": 1}

    # Exported once its ground truth is recorded; the label carries the suggestion.
    truth = {
        "occurred": True,
        "ground_truth_sources": [
            {
                "reference": "https://example.org/follow-up",
                "published_at": (NOW + timedelta(days=1)).isoformat(),
                "kind": "news_followup",
            }
        ],
    }
    assert client.patch(url, json=truth, headers=h).status_code == 200
    db.expire_all()
    export = dataset.build(db, now=NOW + timedelta(days=8))
    notes = [
        ann["note"]
        for row in export.files["events.jsonl"]
        for c in row["assessments"]
        for ann in c["annotations"]
    ]
    assert any("CARCUX suggested verified (start), not followed" in n for n in notes)


# --- Training ----------------------------------------------------------------------------


def _world(db, people, n=20):
    """A careful field worker who is right every time, and a news feed that reports
    every rumour as fact: half the events never happened."""
    a, (careful, other, _) = people["analyst"], people["workers"]
    feed = _feed(db)
    for k in range(n):
        happened = k % 2 == 0
        e = _event(db, a, title=f"Situation number {k}", occurred=happened, hours=k)
        _report(db, e, careful, a, relation=S if happened else C)
        _signal(db, e, feed, a, relation=S)
        if k % 4 == 0:
            _report(db, e, other, a, relation=S)
    db.commit()
    return feed


def test_training_needs_resolved_events(client, db, people):
    h = people["admin_headers"]
    r = client.post("/api/v1/assessment/model/train", headers=h)
    assert r.status_code == 422 and "at least 10" in r.json()["detail"]
    r = client.post("/api/v1/assessment/model/train", headers=people["analyst_headers"])
    assert r.status_code == 403


def test_trained_model_learns_who_to_trust(client, db, people):
    feed = _world(db, people)
    a, careful = people["analyst"], people["workers"][0]
    # A new event only the rumour-prone feed reports.
    e = _event(db, a, title="Only the feed says so")
    _signal(db, e, feed, a)
    db.commit()
    before = _suggestion(client, people, e)
    assert before["method"] == "start" and before["probability"] == pytest.approx(0.75)

    r = client.post("/api/v1/assessment/model/train", headers=people["admin_headers"])
    assert r.status_code == 201, r.text
    model = r.json()
    assert model["events"] == 20 and model["happened"] == 10 and model["active"]
    m = model["metrics"]
    if m.get("model_brier") is not None:
        assert m["model_brier"] <= m["majority_brier"]

    after = _suggestion(client, people, e)
    assert after["method"] == "model" and after["model_id"] == model["id"]
    assert after["probability"] < 0.75  # the feed has been wrong half the time
    reason = after["reasons"][0]
    assert reason["learned"] and reason["reliability"] < 0.75

    e2 = _event(db, a, title="The careful worker saw it")
    _report(db, e2, careful, a)
    db.commit()
    assert _suggestion(client, people, e2)["probability"] > 0.8

    status = client.get("/api/v1/assessment/model", headers=people["analyst_headers"]).json()
    assert status["method"] == "model" and status["resolved_events"] == 20
    assert (
        client.post(
            "/api/v1/assessment/model/deactivate", headers=people["admin_headers"]
        ).status_code
        == 204
    )
    assert _suggestion(client, people, e)["method"] == "start"
    trained = db.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.ASSESSMENT_TRAINED)
    ).all()
    assert len(trained) == 2


def test_held_out_evaluation_compares_with_start_and_majority():
    resolved = []
    for k in range(40):
        happened = k % 2 == 0
        vs = [
            _v(f"careful{k % 3}", vote=1 if happened else -1, relation=S if happened else C),
            _v("credulous", kind="news"),
        ]
        resolved.append((vs, happened))
    m = assess.evaluate(resolved[:30], resolved[30:])
    assert m["held_out_events"] == 10
    assert m["model_brier"] < m["majority_brier"]
    assert math.isfinite(m["start_brier"])


def test_cli_training(db, people, monkeypatch, capsys):
    from app import cli
    from app.core.config import get_settings
    from tests.conftest import TEST_DATABASE_URL

    monkeypatch.setenv("CARCUX_DATABASE_URL", TEST_DATABASE_URL)
    get_settings.cache_clear()
    try:
        assert cli.main(["train-assessment"]) == 1
        assert "at least 10" in capsys.readouterr().err
        _world(db, people)
        assert cli.main(["train-assessment"]) == 0
        assert "trained on 20 events with ground truth (10 happened)" in capsys.readouterr().out
    finally:
        get_settings.cache_clear()
