"""Fusion development checks on SYNTHETIC data: reweighting, folds, crowd benchmark, and
that cross-validation never reads the J24 test claims."""

import csv
import random

from carcux_data.j24 import fusion_dev as fd


def test_reweight_switches_parts_off():
    votes = {"g": [
        {"outlet": "a", "vote": 1.0, "conf": 0.8, "title": "Police killed seven at the bridge"},
        {"outlet": "b", "vote": 1.0, "conf": 0.6,
         "title": "Police killed seven at the bridge, says report"},
        {"outlet": "c", "vote": -0.5, "conf": 0.5, "title": "Was anyone killed? Doubts"},
    ]}  # fmt: skip
    full = fd.reweight(votes)["g"]
    assert full[0]["weight"] == 0.4 and full[1]["weight"] == 0.3  # one story, two copies
    assert [v["weight"] for v in fd.reweight(votes, copies=False)["g"]][:2] == [0.8, 0.6]
    assert {v["weight"] for v in fd.reweight(votes, copies=False, conf=False)["g"]} == {1.0}
    assert len(fd.reweight(votes, questions=False)["g"]) == 2
    assert votes["g"][0].get("weight") is None  # the input is left alone


def test_folds_cover_everything_once():
    items = [f"g{i}" for i in range(23)]
    parts = fd.folds(items, 5)
    assert sorted(x for p in parts for x in p) == sorted(items)
    assert parts == fd.folds(list(reversed(items)), 5)  # same split whatever the order


def test_benchmark_on_synthetic_crowd(tmp_path):
    rng = random.Random(3)  # noqa: S311
    answers, truth = [], []
    for i in range(150):
        t = int(rng.random() < 0.4)
        truth.append({"question": f"q{i}", "truth": t})
        for w, acc in (("w1", 0.9), ("w2", 0.85), ("spammer", 0.15)):
            a = t if rng.random() < acc else 1 - t
            answers.append({"question": f"q{i}", "worker": w, "answer": a})
    for name, rows in (("answer.csv", answers), ("truth.csv", truth)):
        with (tmp_path / name).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    rep = fd.benchmark(tmp_path / "answer.csv", tmp_path / "truth.csv", log=lambda m: None)
    m = rep["methods"]
    assert rep["items"] == 150 and rep["workers"] == 3
    assert m["carcux"]["with_votes"]["auc"] > m["majority"]["with_votes"]["auc"]
    assert "carcux" in rep["methods_20pct_known"]


def test_cross_validation_never_sees_test_claims(tmp_path, monkeypatch):
    truth = {f"g{i}": i % 2 for i in range(40)}
    test = set(list(truth)[:12])
    seen = set()

    def fake_votes(*a, **k):
        return {g: [{"outlet": "o", "vote": 1.0 if t else -1.0, "weight": 1.0, "conf": 1.0,
                     "title": ""}] for g, t in truth.items()}  # fmt: skip

    def spy(fn):
        def wrapped(votes, claims, train, **k):
            seen.update(claims)
            seen.update(train)
            return fn(votes, claims, train=train)

        return wrapped

    monkeypatch.setattr(fd, "truth_labels", lambda p: truth)
    monkeypatch.setattr(fd, "split", lambda groups: test)
    monkeypatch.setattr(fd, "load_votes", fake_votes)
    monkeypatch.setattr(fd, "claim_sources", lambda p: {})
    monkeypatch.setattr(fd, "VARIANTS", {n: (spy(f), o) for n, (f, o) in fd.VARIANTS.items()})
    rep = fd.cross_validate(tmp_path, tmp_path / "c.jsonl", log=lambda m: None)
    assert rep["training_claims"] == 28
    assert not seen & test
    assert (tmp_path / "fusion" / "cv_auto.json").exists()


def test_dawid_skene_learns_the_true_share():
    from carcux_data.j24 import fusion as fu

    rng = random.Random(5)  # noqa: S311
    truth, votes = {}, {}
    for i in range(300):
        t = int(rng.random() < 0.15)
        truth[f"g{i}"] = t
        votes[f"g{i}"] = [
            {"outlet": o, "vote": 1.0 if (rng.random() < acc) == bool(t) else -1.0, "weight": 1.0}
            for o, acc in (("a", 0.8), ("b", 0.75), ("c", 0.7))
        ]
    claims = sorted(truth)
    learned = fu.dawid_skene(votes, claims)
    fixed = fu._em(votes, claims, clamp={}, prior=0.5)

    def acc(s):
        return sum((s[g] >= 0.5) == bool(truth[g]) for g in claims) / len(claims)

    assert acc(learned) > acc(fixed)


def test_choose_prior_and_claim_sources(tmp_path):
    import json

    from carcux_data.j24 import fusion as fu

    rng = random.Random(7)  # noqa: S311
    train, votes = {}, {}
    for i in range(60):
        t = int(rng.random() < 0.5)
        train[f"g{i}"] = t
        votes[f"g{i}"] = [{"outlet": "a", "vote": 1.0 if t else -1.0, "weight": 1.0}]
    name, res = fu.choose_prior(votes, train)
    assert name in fu.PRIORS and set(res) == set(fu.PRIORS)
    rows = [
        {"claim_id": "1", "claim_group": "g", "in_scope": "yes", "source": "fact_check"},
        {"claim_id": "2", "claim_group": "g", "in_scope": "yes", "source": "ohchr"},
        {"claim_id": "3", "claim_group": "h", "in_scope": "yes", "source": "fact_check"},
    ]
    p = tmp_path / "c.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    assert fu.claim_sources(p) == {"g": "ohchr", "h": "fact_check"}


def test_tab_format_and_unlabelled_items(tmp_path):
    (tmp_path / "labels.txt").write_text(
        "w1\ti1\tYes\nw2\ti1\tYes\nw1\ti2\tNo\nw2\ti2\tNo\nw1\ti3\tYes\n", encoding="utf-8"
    )
    (tmp_path / "gold.txt").write_text("i1\tYes\ni2\tNo\n", encoding="utf-8")
    truth, votes = fd.load_crowd(tmp_path / "labels.txt", tmp_path / "gold.txt", "Yes")
    assert truth == {"i1": 1, "i2": 0}
    assert set(votes) == {"i1", "i2", "i3"}  # i3 has no gold but still teaches the EM
    assert votes["i1"][0] == {"outlet": "w1", "vote": 1.0, "weight": 1.0, "conf": 1.0,
                              "title": ""}  # fmt: skip


def test_empirical_bayes_variant_and_trust_metrics():
    from carcux_data.j24 import fusion as fu

    rng = random.Random(11)  # noqa: S311
    truth, votes = {}, {}
    for i in range(200):  # many sources, each seen only a few times: the sparse case
        t = int(rng.random() < 0.3)
        truth[f"g{i}"] = t
        votes[f"g{i}"] = [
            {"outlet": f"s{rng.randrange(150)}", "weight": 1.0,
             "vote": 1.0 if (rng.random() < 0.8) == bool(t) else -1.0}
            for _ in range(3)
        ]  # fmt: skip
    claims = sorted(truth)
    train = {g: truth[g] for g in claims[:120]}
    assert fu.choose_strength(votes, claims, train) in fu.EB_STRENGTHS
    s = fu.carcux_eb(votes, claims, train=train)
    assert all(0 < s[g] < 1 for g in claims[120:])
    m = fu.metrics([truth[g] for g in claims[120:]], [s[g] for g in claims[120:]])
    assert 0 <= m["ece"] <= 1 and 0 <= m["acc_at_80pct"] <= 1


def test_snow_format_and_sparsity(tmp_path):
    rng = random.Random(13)  # noqa: S311
    lines = ["!amt_annotation_ids\t!amt_worker_ids\torig_id\tresponse\tgold"]
    for i in range(60):
        t = int(rng.random() < 0.5)
        for w in range(6):
            a = t if rng.random() < 0.8 else 1 - t
            lines.append(f"x{i}{w}\tw{w}\t{i}\t{a}\t{t}")
    f = tmp_path / "rte.standardized.tsv"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    truth, votes = fd.load_crowd(f, f)
    assert len(truth) == 60 and all(len(v) == 6 for v in votes.values())
    rep = fd.sparsity(f, f, seeds=1, log=lambda m: None)
    assert set(rep["budgets"]) == {"1", "2", "3", "5", "all"}
    assert rep["budgets"]["all"]["carcux"]["auc"] >= rep["budgets"]["1"]["carcux"]["auc"]


def test_platt_stays_bounded_and_softens_overconfidence():
    from carcux_data.j24 import fusion as fu

    rng = random.Random(17)  # noqa: S311
    y, p = [], []
    for _ in range(400):  # says 95% but is right only 70% of the time
        t = int(rng.random() < 0.5)
        right = rng.random() < 0.7
        y.append(t)
        p.append(0.95 if (t == 1) == right else 0.05)
    a, b = fu.fit_platt(y, p)
    assert 0.05 <= a < 1  # confidence is softened
    sep = fu.fit_platt([1, 0] * 50, [0.999, 0.001] * 50)  # perfectly separable
    assert sep[0] <= 3.0 and abs(sep[1]) <= 5.0


def test_simulation_on_a_synthetic_structure(tmp_path, monkeypatch):
    import json

    rng = random.Random(21)  # noqa: S311
    truth, cands, copies = {}, [], []
    outlets = [f"o{i}" for i in range(12)]
    n = 0
    for g in range(60):
        gid = f"g{g}"
        truth[gid] = int(rng.random() < 0.3)
        origin = None
        for j in range(8):
            n += 1
            pid = f"p{n:05d}"
            cands.append({"pair_id": pid, "claim_group": gid, "outlet": rng.choice(outlets),
                          "title": f"SYNTHETIC {gid} {j}"})  # fmt: skip
            story = origin if (origin and j % 4 == 1) else pid  # some articles are copies
            origin = origin or pid
            copies.append({"pair_id": pid, "story": story})
    (tmp_path / "matches").mkdir()
    for name, rows in (("candidates.jsonl", cands), ("copies.jsonl", copies)):
        (tmp_path / "matches" / name).write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )
    monkeypatch.setattr(fd, "truth_labels", lambda p: truth)
    monkeypatch.setattr(fd, "split", lambda groups: set(sorted(groups)[:15]))
    rep = fd.simulate(tmp_path, tmp_path / "c.jsonl", seeds=2, log=lambda m: None)
    assert rep["structure"]["training_claims"] == 45
    assert rep["structure"]["stories"] < rep["structure"]["articles"]
    real = rep["with real copying"]
    assert set(real) == set(fd.SIM_VARIANTS)
    assert real["carcux (text copies)"]["auc"][0] > 0.5
    assert (tmp_path / "fusion" / "sim_preview.json").exists()
