"""Development checks for the fusion methods that never touch the J24 test claims.

- `cross_validate`: k-fold cross-validation inside the J24 training claim groups (the test
  split is left out entirely), with ablations of CARCUX: no copy discount, no stance
  confidence, a flat prior on outlet rates, and question votes dropped.
- `benchmark`: the same methods on a public crowdsourcing truth-inference dataset
  (answer.csv: question, worker, answer in {0, 1}; truth.csv: question, truth), where
  workers play the part of outlets. Datasets: Zheng et al., PVLDB 10(5), 2017.
"""

from __future__ import annotations

import csv
import json
import random
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from carcux_data.j24.ci import interval
from carcux_data.j24.fusion import (
    METHODS,
    SEED,
    _em,
    copy_clusters,
    load_votes,
    metrics,
    split,
    truth_labels,
)


def reweight(votes: dict[str, list[dict]], *, copies: bool = True, conf: bool = True,
             questions: bool = True) -> dict[str, list[dict]]:  # fmt: skip
    """The votes again, with the copy discount and stance confidence switched on or off."""
    out = {}
    for g, vs in votes.items():
        vs = [dict(v) for v in vs if questions or v["vote"] != -0.5]
        clusters = copy_clusters(vs) if copies else list(range(len(vs)))
        sizes = defaultdict(int)
        for k in clusters:
            sizes[k] += 1
        for v, k in zip(vs, clusters, strict=True):
            v["weight"] = (v.get("conf", 1.0) if conf else 1.0) / sizes[k]
        out[g] = vs
    return out


def _carcux_flat(votes, claims, train, **_):
    base = min(max(sum(train.values()) / len(train), 0.05), 0.95) if train else 0.5
    return _em(votes, claims, clamp=train, prior=base, a0=(1.0, 1.0))


VARIANTS: dict[str, tuple[Callable, dict]] = {
    **{name: (fn, {}) for name, fn in METHODS.items()},
    "carcux_no_copy": (METHODS["carcux"], {"copies": False}),
    "carcux_no_conf": (METHODS["carcux"], {"conf": False}),
    "carcux_no_questions": (METHODS["carcux"], {"questions": False}),
    "carcux_flat_prior": (_carcux_flat, {}),
}


def folds(items: list[str], k: int) -> list[list[str]]:
    g = sorted(items)
    random.Random(SEED).shuffle(g)  # noqa: S311 - a reproducible split, not security
    return [g[i::k] for i in range(k)]


def _pooled(truth: dict[str, int], votes, claims: list[str], parts: list[list[str]],
            variants: dict) -> dict[str, dict]:  # fmt: skip
    """Out-of-fold scores for every variant, and their metrics with bootstrap intervals."""
    report = {}
    for name, (fn, opts) in variants.items():
        vv = reweight(votes, **opts) if opts else votes
        scores = {}
        for part in parts:
            held = set(part)
            train = {g: t for g, t in truth.items() if g not in held}
            s = fn(vv, claims, train=train)
            scores.update({g: s[g] for g in part})
        ids = [g for p in parts for g in p]
        covered = [g for g in ids if vv.get(g)]
        report[name] = {"all": metrics([truth[g] for g in ids], [scores[g] for g in ids]),
                        "with_votes": metrics([truth[g] for g in covered],
                                              [scores[g] for g in covered])}  # fmt: skip

        def auc_of(gs, scores=scores):
            return metrics([truth[g] for g in gs], [scores[g] for g in gs])["auc"]

        report[name]["with_votes"]["auc_95"] = interval(covered, auc_of)
    return report


def cross_validate(out: Path, claims_path: Path, *, k: int = 5, stances: str = "auto",
                   sheets=None, key=None, log: Callable[[str], None] = print) -> dict:  # fmt: skip
    truth_all = truth_labels(claims_path)
    test = split(list(truth_all))
    truth = {g: t for g, t in truth_all.items() if g not in test}  # training claims only
    votes = load_votes(out, stances=stances, sheets=sheets, key=key)
    votes = {g: v for g, v in votes.items() if g in truth}
    claims = sorted(truth)
    report = {"stances": stances, "folds": k, "training_claims": len(claims),
              "with_votes": sum(1 for g in claims if votes.get(g)),
              "true_share": sum(truth.values()) / max(len(truth), 1),
              "methods": _pooled(truth, votes, claims, folds(claims, k), VARIANTS)}  # fmt: skip
    folder = out / "fusion"
    folder.mkdir(exist_ok=True)
    (folder / f"cv_{stances}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    log(table(report))
    return report


def load_crowd(answers: Path, truth_file: Path) -> tuple[dict[str, int], dict[str, list[dict]]]:
    with truth_file.open(encoding="utf-8") as f:
        truth = {r["question"]: int(r["truth"]) for r in csv.DictReader(f)}
    votes: dict[str, list[dict]] = defaultdict(list)
    with answers.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["question"] in truth and r["answer"] in ("0", "1"):
                v = 1.0 if r["answer"] == "1" else -1.0
                votes[r["question"]].append({"outlet": r["worker"], "vote": v, "weight": 1.0,
                                             "conf": 1.0, "title": ""})  # fmt: skip
    return truth, dict(votes)


def benchmark(answers: Path, truth_file: Path, *, k: int = 5,
              log: Callable[[str], None] = print) -> dict:  # fmt: skip
    """Each fold in turn is scored with the other folds' truth known (80% supervision), and
    again with only one other fold known (20%), the sparse case."""
    truth, votes = load_crowd(answers, truth_file)
    claims = sorted(truth)
    parts = folds(claims, k)
    base = {n: VARIANTS[n] for n in METHODS}
    report = {"items": len(claims), "workers": len({v["outlet"] for vs in votes.values()
                                                     for v in vs}),  # fmt: skip
              "answers_per_item": sum(map(len, votes.values())) / max(len(votes), 1),
              "true_share": sum(truth.values()) / max(len(truth), 1),
              "methods": _pooled(truth, votes, claims, parts, base)}  # fmt: skip
    sparse = {}
    for name, (fn, _) in base.items():
        scores = {}
        for i, part in enumerate(parts):
            known = set(parts[(i + 1) % k])
            s = fn(votes, claims, train={g: truth[g] for g in known})
            scores.update({g: s[g] for g in part})
        ids = [g for p in parts for g in p]
        sparse[name] = metrics([truth[g] for g in ids], [scores[g] for g in ids])
    report["methods_20pct_known"] = sparse
    log(table(report))
    return report


def table(report: dict) -> str:
    lines = [f"{'method':22s} {'AUC':>6s} {'95% CI':>15s} {'acc':>6s} {'F1':>6s} {'Brier':>6s}"]
    for name, m in report["methods"].items():
        w = m["with_votes"]
        ci = w.get("auc_95")
        ci_s = f"[{ci[0]:.3f}, {ci[1]:.3f}]" if ci else ""
        auc = w.get("auc")
        lines.append(f"{name:22s} {auc if auc is None else round(auc, 3)!s:>6s} {ci_s:>15s} "
                     f"{w.get('accuracy', 0):6.3f} {w.get('macro_f1', 0):6.3f} "
                     f"{w.get('brier', 0):6.3f}")  # fmt: skip
    for name, m in report.get("methods_20pct_known", {}).items():
        lines.append(f"{name + ' (20% known)':22s} {m['auc']:6.3f} {'':>15s} "
                     f"{m['accuracy']:6.3f} {m['macro_f1']:6.3f} {m['brier']:6.3f}")  # fmt: skip
    return "\n".join(lines)
