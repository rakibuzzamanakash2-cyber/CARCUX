"""Fusion on SYNTHETIC claims and outlets: truth labels, copy discount, the methods, and
that the test claims never inform the fitted methods."""

import json
import random

from carcux_data.j24 import fusion as fu


def test_truth_comes_only_from_ohchr_and_fact_checkers(tmp_path):
    rows = [
        {
            "claim_id": "o1",
            "claim_group": "o1",
            "in_scope": "yes",
            "source": "ohchr",
            "ohchr_finding": "found",
        },
        {
            "claim_id": "o2",
            "claim_group": "o2",
            "in_scope": "yes",
            "source": "ohchr",
            "ohchr_finding": "relayed",
        },
        {
            "claim_id": "f1",
            "claim_group": "f1",
            "in_scope": "yes",
            "source": "fact_check",
            "verdict": "misleading",
        },
        {
            "claim_id": "f2",
            "claim_group": "f1",
            "in_scope": "yes",
            "source": "fact_check",
            "verdict": "true",
        },
        {
            "claim_id": "f3",
            "claim_group": "f3",
            "in_scope": "no",
            "source": "fact_check",
            "verdict": "false",
        },
    ]
    p = tmp_path / "c.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    assert fu.truth_labels(p) == {"o1": 1}  # relayed, conflicting and out-of-scope: no label


def test_copies_share_one_vote():
    arts = [
        {"title": "Police killed seven at the bridge"},
        {"title": "Police killed seven at the bridge, says report"},
        {"title": "Completely different story about prices"},
    ]
    c = fu.copy_clusters(arts)
    assert c[0] == c[1] != c[2]


def synthetic(n_claims=80, seed=1):
    """Good outlets report the truth, a bad outlet says the opposite."""
    rng = random.Random(seed)  # noqa: S311
    truth, votes = {}, {}
    for i in range(n_claims):
        t = rng.random() < 0.5
        truth[f"g{i}"] = int(t)
        vs = []
        for o, acc in (("good1", 0.9), ("good2", 0.85), ("bad", 0.2)):
            right = rng.random() < acc
            vs.append({"outlet": o, "vote": 1.0 if right == t else -1.0, "weight": 1.0})
        votes[f"g{i}"] = vs
    return truth, votes


def test_learned_reliability_beats_majority_when_an_outlet_lies():
    truth, votes = synthetic()
    claims = sorted(truth)
    test = set(claims[:24])
    train = {g: t for g, t in truth.items() if g not in test}
    y = [truth[g] for g in sorted(test)]
    res = {}
    for name, fn in fu.METHODS.items():
        s = fn(votes, claims, train=train)
        res[name] = fu.metrics(y, [s[g] for g in sorted(test)])["accuracy"]
    assert res["carcux"] >= res["majority"] and res["reliability"] >= res["majority"]
    assert res["carcux"] >= 0.8


def test_clamping_does_not_use_test_truth():
    truth, votes = synthetic()
    claims = sorted(truth)
    train = {g: t for g, t in truth.items() if g not in {"g0"}}
    flipped = dict(train)
    s1 = fu.carcux(votes, claims, train=train)["g0"]
    s2 = fu.carcux(votes, claims, train=flipped)["g0"]
    assert s1 == s2 and 0 < s1 < 1


def test_split_is_fixed():
    gs = [f"g{i}" for i in range(100)]
    assert fu.split(gs) == fu.split(list(reversed(gs))) and len(fu.split(gs)) == 30
