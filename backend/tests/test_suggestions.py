"""Event suggestions: rule until a model is trained, then ranked by the model."""

import uuid
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from sqlalchemy import select

from app import cli
from app.core.config import get_settings
from app.core.event_types import EVENT_TYPE_FAMILY
from app.models.audit import AuditLog
from app.models.event import Event, EventEvidence, EvidenceRelation
from app.models.field_report import FieldReport
from app.models.signal import Signal, Source
from app.models.suggestion import SuggestionModel
from app.models.user import Role, User
from app.services import suggest
from app.services.audit import AuditAction
from tests.conftest import TEST_DATABASE_URL

NOW = datetime.now(UTC).replace(microsecond=0)

# Eight situations around Dhaka. The last one runs for days: its later reports fall
# outside the rule's 48 hours.
SITUATIONS = [
    (
        "Waterlogging at Mirpur 10",
        "waterlogging",
        23.8069,
        90.3687,
        0,
        [
            "knee deep water mirpur 10 circle",
            "mirpur 10 rasta pani te dube ache",
            "water still standing at mirpur 10 roundabout",
        ],
    ),
    (
        "Fire at Kawran Bazar market",
        "fire",
        23.7509,
        90.3935,
        30,
        [
            "fire in kawran bazar kitchen market",
            "kawran bazar e agun lagse",
            "smoke over kawran bazar market, fire service there",
        ],
    ),
    (
        "Road crash at Jatrabari",
        "road_accident",
        23.7106,
        90.4349,
        60,
        [
            "bus truck crash jatrabari flyover",
            "jatrabari accident koyekjon ahoto",
            "crash on jatrabari flyover, traffic stopped",
        ],
    ),
    (
        "Power cut in Uttara",
        "power_outage",
        23.8759,
        90.3795,
        90,
        [
            "no electricity uttara sector 7",
            "uttara te current nai shokal theke",
            "uttara sector 7 blackout continues",
        ],
    ),
    (
        "Gas leak at Tejgaon",
        "building_hazard",
        23.7639,
        90.3925,
        120,
        [
            "gas smell tejgaon industrial area",
            "tejgaon e gas leak er gondho",
            "tejgaon factory gas leak, people moved out",
        ],
    ),
    (
        "Blockade at Shahbag",
        "road_blockage",
        23.7380,
        90.3958,
        150,
        [
            "shahbag intersection blocked by protest",
            "shahbag e oborodh, gari choltese na",
            "shahbag still blocked, long tailback",
        ],
    ),
    (
        "Waterlogging at Dhanmondi 27",
        "waterlogging",
        23.7561,
        90.3743,
        180,
        [
            "dhanmondi 27 road under water",
            "dhanmondi 27 e hatu pani",
            "dhanmondi 27 water knee deep near the mosque",
        ],
    ),
    (
        "Flooding along the Turag at Ashulia",
        "flood",
        23.8990,
        90.3260,
        210,
        [
            "turag river water entering ashulia homes",
            "ashulia te turag er pani barche",
            "ashulia flood water rising along turag embankment",
            "turag embankment at ashulia still flooded, families moved",
        ],
    ),
]


@pytest.fixture
def people(make_user, login):
    analyst = make_user("analyst@office.local", Role.ANALYST)
    worker = make_user("worker@office.local", Role.FIELD_WORKER)
    make_user("admin@office.local", Role.ADMIN)
    return {
        "analyst": analyst,
        "worker": worker,
        "analyst_headers": login("analyst@office.local"),
        "admin_headers": login("admin@office.local"),
    }


def _report(db, worker: User, text: str, lat: float, lon: float, when: datetime, etype):
    r = FieldReport(
        id=uuid.uuid4(),
        client_report_id=uuid.uuid4(),
        reporter_id=worker.id,
        text=text,
        event_type=etype,
        latitude=lat,
        longitude=lon,
        location_accuracy_m=30,
        observed_at=when,
        content_hash="0" * 64,
    )
    db.add(r)
    return r


def build_history(db, people) -> dict[str, Event]:
    """Events with linked reports, as analysts would have made them."""
    events = {}
    for title, etype, lat, lon, hours_ago, texts in SITUATIONS:
        start = NOW - timedelta(hours=hours_ago + 6)
        e = Event(
            id=uuid.uuid4(),
            title=title,
            event_type=etype,
            family=EVENT_TYPE_FAMILY[etype],
            latitude=lat,
            longitude=lon,
            started_at=start,
            created_by_id=people["analyst"].id,
        )
        db.add(e)
        events[title] = e
        long_running = etype == "flood"
        for k, text in enumerate(texts):
            when = start + timedelta(hours=(k * 30 if long_running else k))
            jitter = 0.002 * k
            r = _report(db, people["worker"], text, lat + jitter, lon - jitter, when, etype)
            db.flush()
            db.add(
                EventEvidence(
                    id=uuid.uuid4(),
                    event_id=e.id,
                    field_report_id=r.id,
                    relation=EvidenceRelation.SUPPORTS,
                    linked_by_id=people["analyst"].id,
                )
            )
    db.commit()
    return events


# --- Pieces ----------------------------------------------------------------------------


def _item(text, hours, lat=23.8, lon=90.4, etype=None, key="report:x"):
    return suggest.Item(key, text, NOW + timedelta(hours=hours), lat, lon, 0.0, etype)


def test_identical_text_is_fully_similar_and_unrelated_text_is_not():
    space = suggest.TextSpace(["mirpur 10 pani", "mirpur 10 pani", "kawran bazar agun"])
    a, b, c = space.vectors
    assert space.dot(a, b) == pytest.approx(1.0)
    assert space.dot(a, c) < 0.2


def test_bangla_text_produces_character_grams():
    grams = suggest._grams("মিরপুরে পানি")
    assert grams and all(len(g) >= 2 for g in grams)


def test_time_gap_is_zero_inside_the_event_span_and_grows_outside():
    group = [_item("a", 0, key="event:1"), _item("b", 10, key="report:1")]
    inside = suggest.features(_item("a b", 5), [group])[0]
    after = suggest.features(_item("a b", 30), [group])[0]
    before = suggest.features(_item("a b", -20), [group])[0]
    gap = suggest.NC["log_hours_newest"]
    assert inside[gap] == 0
    assert after[gap] == pytest.approx(np.log1p(20))
    assert before[gap] == pytest.approx(np.log1p(20))


def test_distance_type_and_missing_values():
    group = [
        _item("x", 0, lat=23.80, lon=90.40, etype="fire", key="event:1"),
        _item("y", 0, lat=23.81, lon=90.40, etype="flood", key="report:1"),
    ]
    row = suggest.features(_item("x", 0, lat=23.81, lon=90.40, etype="fire"), [group])[0]
    assert row[suggest.NC["any_located"]] == 1
    assert row[suggest.NC["log_min_km"]] == pytest.approx(0.0, abs=1e-9)
    assert row[suggest.NC["same_type_share"]] == pytest.approx(0.5)
    unknown = suggest.features(_item("x", 0, lat=None, lon=None), [group])[0]
    assert unknown[suggest.NC["any_located"]] == 0
    assert unknown[suggest.NC["type_unknown"]] == 1


def test_logistic_fit_separates_and_round_trips():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(200, len(suggest.NAMES)))
    y = (x[:, 0] - x[:, 2] > 0).astype(int)
    w = suggest.fit_logistic(x, y)
    p = suggest.probability(w, x)
    assert ((p > 0.5) == y).mean() > 0.95
    assert w["coef"][0] > 0 > w["coef"][2]


def test_stored_model_with_other_features_is_refused():
    with pytest.raises(ValueError):
        suggest.probability({"names": ["old"]}, np.zeros((1, 1)))


# --- Through the API -------------------------------------------------------------------


def test_without_a_model_suggestions_use_the_rule(client, db, people):
    events = build_history(db, people)
    e = events["Waterlogging at Mirpur 10"]
    r = _report(db, people["worker"], "water at mirpur 10", e.latitude, e.longitude, NOW, None)
    db.commit()
    got = client.get(
        f"/api/v1/field-reports/{r.id}/candidate-events", headers=people["analyst_headers"]
    ).json()
    assert got and all(c["method"] == "rule" and c["score"] is None for c in got)
    status = client.get("/api/v1/suggestions/model", headers=people["analyst_headers"]).json()
    assert status["method"] == "rule" and status["active"] is None
    assert status["labelled_items"] == sum(len(s[-1]) for s in SITUATIONS)
    assert status["labelled_events"] == len(SITUATIONS)


def test_training_needs_enough_links(client, db, people):
    response = client.post("/api/v1/suggestions/model/train", headers=people["admin_headers"])
    assert response.status_code == 422
    assert "at least" in response.json()["detail"]


def test_only_admins_train(client, db, people):
    response = client.post("/api/v1/suggestions/model/train", headers=people["analyst_headers"])
    assert response.status_code == 403


def test_trained_model_ranks_and_finds_what_the_rule_misses(client, db, people):
    events = build_history(db, people)
    response = client.post("/api/v1/suggestions/model/train", headers=people["admin_headers"])
    assert response.status_code == 201, response.text
    model = response.json()
    assert model["active"] and model["items"] == 25 and model["events"] == 8
    assert model["positives"] >= 25 and model["negatives"] > 0
    assert set(model["metrics"]) >= {"held_out_items"}

    # The flood was marked as ended after its last report, but it was not over: a new
    # report comes three days later. That is outside the rule's 48 hours; the wording
    # and the place still match.
    flood = events["Flooding along the Turag at Ashulia"]
    last = max(link.field_report.observed_at for link in flood.evidence)
    flood.ended_at = last + timedelta(hours=1)
    when = last + timedelta(days=3)
    r = _report(
        db,
        people["worker"],
        "turag water still in ashulia houses",
        flood.latitude + 0.003,
        flood.longitude,
        when,
        "flood",
    )
    db.commit()
    got = client.get(
        f"/api/v1/field-reports/{r.id}/candidate-events", headers=people["analyst_headers"]
    ).json()
    assert got[0]["event"]["id"] == str(flood.id)
    assert got[0]["method"] == "model" and got[0]["model_id"] == model["id"]
    assert got[0]["score"] > 0.5 and got[0]["text_similarity"] > 0.2
    assert got[0]["hours_from_latest"] == pytest.approx(72, abs=0.2)
    assert [c["score"] for c in got] == sorted((c["score"] for c in got), reverse=True)
    assert all(c["score"] >= suggest.MIN_SCORE for c in got)
    # The rule would not have offered it.
    assert all(e.id != flood.id for e, _ in suggest.rules.candidate_events(db, r))

    entry = db.scalar(select(AuditLog).where(AuditLog.action == AuditAction.SUGGESTIONS_TRAINED))
    assert entry.details["items"] == 25


def test_linking_from_a_suggestion_is_recorded(client, db, people):
    events = build_history(db, people)
    client.post("/api/v1/suggestions/model/train", headers=people["admin_headers"])
    e = events["Fire at Kawran Bazar market"]
    r = _report(db, people["worker"], "kawran bazar fire", e.latitude, e.longitude, NOW, "fire")
    db.commit()
    model_id = db.scalar(select(SuggestionModel.id).where(SuggestionModel.active.is_(True)))
    body = {
        "field_report_id": str(r.id),
        "relation": "supports",
        "suggestion": {"rank": 1, "method": "model", "score": 0.9, "model_id": str(model_id)},
    }
    response = client.post(
        f"/api/v1/events/{e.id}/evidence", json=body, headers=people["analyst_headers"]
    )
    assert response.status_code == 201, response.text
    entry = db.scalar(
        select(AuditLog)
        .where(AuditLog.action == AuditAction.EVIDENCE_LINKED)
        .order_by(AuditLog.id.desc())
    )
    assert entry.details["suggestion"]["rank"] == 1
    usage = client.get("/api/v1/suggestions/model", headers=people["analyst_headers"]).json()
    assert usage["from_suggestions"] == {"total": 1, "first": 1, "top3": 1}


def test_retraining_keeps_one_active_model_and_deactivating_restores_the_rule(client, db, people):
    build_history(db, people)
    for _ in range(2):
        assert (
            client.post("/api/v1/suggestions/model/train", headers=people["admin_headers"])
        ).status_code == 201
    status = client.get("/api/v1/suggestions/model", headers=people["analyst_headers"]).json()
    assert status["method"] == "model" and len(status["previous"]) == 1
    client.post("/api/v1/suggestions/model/deactivate", headers=people["admin_headers"])
    status = client.get("/api/v1/suggestions/model", headers=people["analyst_headers"]).json()
    assert status["method"] == "rule" and len(status["previous"]) == 2


def test_signal_without_location_gets_model_suggestions_by_text_and_time(client, db, people):
    events = build_history(db, people)
    client.post("/api/v1/suggestions/model/train", headers=people["admin_headers"])
    source = db.scalar(select(Source).limit(1))
    s = Signal(
        id=uuid.uuid4(),
        source_id=source.id,
        external_id="x1",
        title="Shahbag intersection blocked again by protesters",
        published_at=NOW,
        content_hash="0" * 64,
    )
    db.add(s)
    db.commit()
    got = client.get(
        f"/api/v1/signals/{s.id}/candidate-events", headers=people["analyst_headers"]
    ).json()
    assert got[0]["event"]["id"] == str(events["Blockade at Shahbag"].id)
    assert got[0]["distance_km"] is None


def test_cli_trains(monkeypatch, db, people):
    build_history(db, people)
    monkeypatch.setenv("CARCUX_DATABASE_URL", TEST_DATABASE_URL)
    get_settings.cache_clear()
    try:
        assert cli.main(["train-suggestions"]) == 0
    finally:
        get_settings.cache_clear()
    assert db.scalar(select(SuggestionModel).where(SuggestionModel.active.is_(True)))
