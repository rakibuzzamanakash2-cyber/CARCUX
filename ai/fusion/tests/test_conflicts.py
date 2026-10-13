import json
import random
from datetime import UTC, datetime, timedelta

import pytest

from carcux_fusion import assess, conflict, simulate
from carcux_fusion.data import DETAILS, load

T0 = datetime(2026, 7, 1, 8, tzinfo=UTC)


@pytest.fixture(scope="module")
def sim(tmp_path_factory):
    out = tmp_path_factory.mktemp("sim")
    simulate.generate(out, events=50, contamination=0.3, seed=6)
    return out


# --- Simulator: details ---------------------------------------------------------------------


def test_partly_supporting_links_name_the_wrong_details(sim):
    rels = [json.loads(x) for x in (sim / "relations.jsonl").read_text().splitlines()]
    partly = [r for r in rels if r["gold"]["label"] == "partially_supports"]
    assert partly
    assert all(
        r["gold"]["conflicts"] and set(r["gold"]["conflicts"]) <= set(DETAILS) for r in partly
    )
    assert all("conflicts" not in r["gold"] for r in rels if r["gold"]["label"] == "supports")


def test_facts_only_for_events_that_happened(sim):
    data = load(sim)
    for e in data.events.values():
        assert bool(e.facts) == e.occurred
        assert set(e.gold_labels) == {"T+1h", "T+6h", "T+24h", "final"}
    labels = {lab for e in data.events.values() for lab in e.gold_labels.values()}
    assert "partially_verified" in labels


def test_details_do_not_change_anything_else(monkeypatch):
    """Details use their own random stream: items, votes and times are as without them."""
    a = simulate._Sim(30, 0.3, 9)
    a.run()
    original = random.Random

    def other_stream(seed=None):
        return original(seed + 1 if seed == 9 * 7919 + 17 else seed)

    monkeypatch.setattr(simulate.random, "Random", other_stream)
    b = simulate._Sim(30, 0.3, 9)
    b.run()

    def shape(sim):
        return [(i["obs_id"], i["_vote"], i["_when"], i["_source"]["source_id"]) for i in sim.items]

    assert shape(a) == shape(b)
    assert [i["_claims"] for i in a.items] != [i["_claims"] for i in b.items]


def test_copies_repeat_their_origins_details(sim):
    data = load(sim)
    for child, (origin, _) in data.dependences.items():
        assert data.observations[child].claims == data.observations[origin].claims


# --- Conflict detection ---------------------------------------------------------------------


def _claim(detail, value, rate=0.8, wrong=False, minutes=0):
    import math

    return conflict.Claim(
        detail,
        value,
        math.log(rate / (1 - rate)),
        rate,
        f"OBS-{minutes:07d}",
        T0 + timedelta(minutes=minutes),
        wrong,
    )


def test_agreement_rules():
    assert conflict.agrees("affected_count", 100, 120)
    assert not conflict.agrees("affected_count", 100, 300)
    assert not conflict.agrees("casualty_count", 2, 3)
    assert conflict.agrees("magnitude", "knee-deep", "knee-deep")


def test_dispute_needs_two_credible_sources_that_disagree():
    assert conflict.disputed([_claim("casualty_count", 2), _claim("casualty_count", 9)])
    assert not conflict.disputed([_claim("casualty_count", 2), _claim("casualty_count", 2)])
    # A low-reliability source disagreeing is not a dispute.
    assert not conflict.disputed([_claim("casualty_count", 2), _claim("casualty_count", 9, 0.2)])
    assert conflict.disputed_annotated(
        [_claim("cause", "gas leak"), _claim("cause", "unknown", wrong=True)]
    )


def test_estimates_weighted_median_and_mode():
    nums = [
        _claim("affected_count", 100, 0.9),
        _claim("affected_count", 110, 0.9),
        _claim("affected_count", 900, 0.55),
    ]
    assert conflict.estimate(nums) in (100, 110)
    cats = [
        _claim("cause", "gas leak", 0.95),
        _claim("cause", "unknown", 0.6),
        _claim("cause", "unknown", 0.6, minutes=1),
    ]
    assert conflict.estimate(cats) == "gas leak"  # one reliable source outweighs two weak
    assert conflict.estimate(cats, weighted=False) == "unknown"
    assert conflict.estimate([]) is None


def test_claims_count_each_cascade_once(sim):
    data = load(sim)
    event = max(data.events.values(), key=lambda e: len(e.evidence))
    never = datetime.max.replace(tzinfo=UTC)
    every = conflict.claims(data, event, never, data.dependences, one_per_cascade=False)
    once = conflict.claims(data, event, never, data.dependences)
    assert sum(map(len, once.values())) <= sum(map(len, every.values()))


# --- Assessment ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ((0.9, 3, 2, 0, False), "verified"),
        ((0.9, 3, 2, 0, True), "partially_verified"),
        ((0.1, 3, 0, 2, False), "refuted"),
        ((0.5, 3, 1, 1, False), "conflicting"),
        ((0.5, 3, 1, 0, False), "unverified"),
        ((0.5, 0, 0, 0, False), "insufficient_evidence"),
    ],
)
def test_label_rules(args, expected):
    assert assess.label(*args, high=0.8, low=0.2) == expected


def test_assessment_end_to_end(sim, tmp_path):
    out = tmp_path / "a.json"
    assert assess.main([str(sim), "--folds", "4", "--json", str(out)]) == 0
    r = json.loads(out.read_text())
    final = r["checkpoints"]["final"]
    assert set(final["assessment"]) == set(assess.VARIANTS)
    for s in final["assessment"].values():
        assert 0 <= s["macro_f1"] <= 1 and 0 <= s["wrongly_verified"] <= 1
    # Without conflict modelling nothing can be called partly verified.
    assert final["assessment"]["probability only"]["partially_verified_f1"] == 0
    assert set(final["details"]) == set(assess.STRATEGIES)


def test_assess_needs_a_dataset_or_simulate(capsys):
    with pytest.raises(SystemExit):
        assess.main([])


def test_assessment_survives_a_detail_hidden_by_a_wrong_copy_link(sim, monkeypatch):
    """A mis-detected copy can hide a detail from the one-per-cascade view: no estimate
    must count as a miss, not crash."""
    real = conflict.estimates

    def lossy(*args, **kwargs):
        out = real(*args, **kwargs)
        for est in out.values():
            est["weighted"] = None
        return out

    monkeypatch.setattr(conflict, "estimates", lossy)
    r = assess.run(load(sim), k=3)
    assert r["checkpoints"]["final"]["details"]["weighted"] == 0.0
