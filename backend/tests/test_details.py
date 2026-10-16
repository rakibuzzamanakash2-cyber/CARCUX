"""Details found in report and signal text: shown with the item, compared across an
event's sources by the assessment suggestion, and exported as observation claims."""

import uuid
from datetime import timedelta

import pytest

from app.extraction import Claim
from app.models.event import Assessment, EvidenceRelation
from app.models.signal import Signal, Source
from app.services import assess, dataset
from app.services import details as stated
from tests.test_assessment import NOW, S, _event, _feed, _report, _signal, _suggestion, _v
from tests.test_assessment import people as people  # noqa: F401 (fixture)


def _with(vote: assess.Vote, *claims: Claim) -> assess.Vote:
    return assess.Vote(*[getattr(vote, f) for f in ("source_key", "source_type", "source_name",
                       "vote", "relation", "conflicts", "at")], details=claims)  # fmt: skip


# --- Pieces ------------------------------------------------------------------------------


def test_agreement_follows_the_guideline():
    assert stated.agrees("affected_count", 100, 119)
    assert not stated.agrees("affected_count", 100, 130)
    assert not stated.agrees("casualty_count", 2, 5)
    assert stated.agrees("casualty_count", 0, 0)
    assert stated.agrees("cause", "unknown", "gas leak")
    assert not stated.agrees("magnitude", "knee-deep", "waist-deep")


def test_headline_and_text():
    assert stated.headline_and_text("Fire at Bangabazar", None) == "Fire at Bangabazar"
    assert stated.headline_and_text("Fire", "Fire at Bangabazar, 3 dead") == (
        "Fire at Bangabazar, 3 dead"
    )
    assert stated.headline_and_text("Fire", "3 dead") == "Fire. 3 dead"


def test_credible_sources_disagreeing_is_a_detected_dispute():
    deaths = lambda n: Claim("casualty_count", n, "deaths", f"{n} killed")  # noqa: E731
    vs = [_with(_v("a"), deaths(3)), _with(_v("b"), deaths(20)), _v("c")]
    summaries, detected = assess.summarise_details(vs, assess.STARTING)
    assert detected == ["casualty_count"]
    (d,) = summaries
    assert d.disputed and {s.value for s in d.statements} == {3, 20}
    p = assess.STARTING.probability(vs)
    assert assess.label_for(p, vs, assess.STARTING, detected) == (
        Assessment.PARTIALLY_VERIFIED,
        ["casualty_count"],
    )


def test_a_count_that_rose_over_days_is_not_a_dispute():
    # Guideline v0.4: counts are compared only when said within 12 hours of each other,
    # and the estimate is the count as it stands now.
    deaths = lambda n: Claim("casualty_count", n, "deaths", f"{n} killed")  # noqa: E731

    def at(vote, hours):
        return assess.Vote(*[getattr(vote, f) for f in ("source_key", "source_type",
                           "source_name", "vote", "relation", "conflicts")],
                           NOW + timedelta(hours=hours), vote.details)  # fmt: skip

    vs = [
        at(_with(_v("a"), deaths(23)), 0),
        at(_with(_v("b"), deaths(52)), 72),
        at(_with(_v("c"), deaths(54)), 80),
    ]
    (d,), detected = assess.summarise_details(vs, assess.STARTING)
    assert detected == [] and not d.disputed
    assert d.estimate in (52, 54) and {s.value for s in d.statements} == {23, 52, 54}
    # The same two counts said on the same day are a dispute.
    vs.append(at(_with(_v("d"), deaths(20)), 79))
    _, detected = assess.summarise_details(vs, assess.STARTING)
    assert detected == ["casualty_count"]


def test_an_unreliable_source_stating_otherwise_is_not_a_dispute():
    w = assess.Weights(rates={"bad": 0.2})
    depth = lambda v: Claim("magnitude", v, None, v)  # noqa: E731
    vs = [
        _with(_v("a"), depth("knee-deep")),
        _with(_v("b"), depth("knee-deep")),
        _with(_v("bad"), depth("above-head")),
    ]
    summaries, detected = assess.summarise_details(vs, w)
    assert detected == [] and summaries[0].estimate == "knee-deep"


def test_estimates_weigh_sources_by_reliability():
    w = assess.Weights(rates={"good": 0.95, "ok1": 0.6, "ok2": 0.6})
    affected = lambda n: Claim("affected_count", n, "people", str(n))  # noqa: E731
    vs = [
        _with(_v("good"), affected(500)),
        _with(_v("ok1"), affected(5000)),
        _with(_v("ok2"), affected(5100)),
    ]
    (d,), _ = assess.summarise_details(vs, w)
    assert d.estimate == 500  # one reliable source outweighs two middling ones


def test_denials_details_are_not_counted():
    deny = assess.Vote("d", "news", "d", -1, EvidenceRelation.CONTRADICTS, (), NOW,
                       (Claim("casualty_count", 0, "deaths", "no casualties"),))  # fmt: skip
    summaries, detected = assess.summarise_details([_v("a"), deny], assess.STARTING)
    assert summaries == [] and detected == []


# --- In the product ----------------------------------------------------------------------------


def test_reports_and_signals_show_their_details(client, db, people):
    a, (w1, _, _) = people["analyst"], people["workers"]
    e = _event(db, a)
    link = _report(db, e, w1, a, text="Mirpur 10 e hatu pani, 3 jon mara geche")
    feed = _feed(db)
    _signal(db, e, feed, a)
    sig = db.query(Signal).filter(Signal.source_id == feed.id).one()
    sig.title = "Fire at Bangabazar"
    sig.text = "A massive fire gutted 40 shops; cause: electrical short circuit"
    db.commit()
    h = people["analyst_headers"]
    r = client.get(f"/api/v1/field-reports/{link.field_report_id}", headers=h).json()
    assert {(d["attribute"], d["value"]) for d in r["details"]} == {
        ("magnitude", "knee-deep"),
        ("casualty_count", 3),
    }
    assert next(d for d in r["details"] if d["attribute"] == "magnitude")["surface"] == "hatu pani"
    s = client.get(f"/api/v1/signals/{sig.id}", headers=h).json()
    assert {(d["attribute"], d["value"]) for d in s["details"]} == {
        ("magnitude", "large"),
        ("cause", "electrical short circuit"),
    }


def test_suggestion_detects_disputed_details_from_the_texts(client, db, people):
    a, (w1, w2, w3) = people["analyst"], people["workers"]
    e = _event(db, a)
    for worker, text in (
        (w1, "Kawran bazar e agun, 3 jon mara geche"),
        (w2, "কারওয়ান বাজারে আগুন, ২০ জন নিহত"),
        (w3, "Fire at Kawran Bazar market, many people there"),
    ):
        _report(db, e, worker, a, text=text)
    db.commit()
    s = _suggestion(client, people, e)
    assert s["label"] == "partially_verified"
    assert s["disputed"] == s["disputed_detected"] == ["casualty_count"]
    (d,) = s["details"]
    assert d["attribute"] == "casualty_count" and d["disputed"] is True
    assert {(x["value"], x["unit"]) for x in d["statements"]} == {(3, "deaths"), (20, "deaths")}
    assert all(x["source"].startswith("Field worker") for x in d["statements"])


def test_agreeing_details_are_estimated_not_disputed(client, db, people):
    a, (w1, w2, _) = people["analyst"], people["workers"]
    e = _event(db, a)
    _report(db, e, w1, a, text="প্রায় ৫০০ পরিবার পানিবন্দী, হাঁটুসমান পানি")
    _report(db, e, w2, a, text="around 520 families marooned, knee-deep water")
    db.commit()
    s = _suggestion(client, people, e)
    assert s["label"] == "verified" and s["disputed"] == []
    est = {d["attribute"]: (d["estimate"], d["unit"], d["disputed"]) for d in s["details"]}
    assert est["magnitude"] == ("knee-deep", None, False)
    assert est["affected_count"][1:] == ("households", False)
    assert est["affected_count"][0] in (500, 520)


def test_export_carries_denials_and_details(db, people):
    a, (w1, _, _) = people["analyst"], people["workers"]
    e = _event(db, a, occurred=False)
    follow_up = (NOW + timedelta(days=1)).isoformat()
    e.ground_truth_sources = [
        {"reference": "https://example.org/x", "published_at": follow_up, "kind": "news_followup"}
    ]
    text = "Tejgaon e building dhoshe nai, eta gujob"
    _report(db, e, w1, a, relation=EvidenceRelation.CONTRADICTS, text=text)
    feed = _feed(db, "Daily Sim")
    _signal(db, e, feed, a, relation=S)
    db.query(Signal).filter(Signal.source_id == feed.id).one().text = "২ জন নিহত"
    db.commit()
    export = dataset.build(db, now=NOW + timedelta(days=8))
    obs = export.files["observations.jsonl"]
    report = next(o for o in obs if o["reference"].startswith("carcux:field_report:"))
    assert report["claims"][0] == {"attribute": "occurrence", "value": False, "surface": "gujob"}
    assert report["language"] == "bn-Latn"
    sig = next(o for o in obs if not o["reference"].startswith("carcux:field_report:"))
    assert {"attribute": "casualty_count", "value": 2, "unit": "deaths",
            "surface": "২ জন নিহত"} in sig["claims"]  # fmt: skip


@pytest.mark.parametrize("kind", ["field", "news"])
def test_vote_carries_only_comparable_details(db, people, kind):
    a, (w1, _, _) = people["analyst"], people["workers"]
    e = _event(db, a)
    if kind == "field":
        _report(db, e, w1, a, text="pani ekhono barche, hatu pani, eta gujob")
    else:
        feed = db.query(Source).first() or _feed(db)
        _signal(db, e, feed, a)
        db.query(Signal).one().text = "pani ekhono barche, hatu pani"
    db.commit()
    db.refresh(e)
    (v,) = assess.votes(e)
    assert [c.attribute for c in v.details] == ["magnitude"]  # not status, not occurrence
    assert uuid.UUID(str(e.id))
