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
    carcux_eb,
    claim_sources,
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
    "carcux_eb": (carcux_eb, {}),
}


def folds(items: list[str], k: int) -> list[list[str]]:
    g = sorted(items)
    random.Random(SEED).shuffle(g)  # noqa: S311 - a reproducible split, not security
    return [g[i::k] for i in range(k)]


def _pooled(truth: dict[str, int], votes, claims: list[str], parts: list[list[str]],
            variants: dict, ci: bool = True) -> dict[str, dict]:  # fmt: skip
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

        if ci:
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
    src = claim_sources(claims_path)
    covered = [g for g in claims if votes.get(g)]
    report["reference_claim_source_only"] = metrics(
        [truth[g] for g in covered], [1.0 if src.get(g) == "ohchr" else 0.0 for g in covered]
    )
    folder = out / "fusion"
    folder.mkdir(exist_ok=True)
    (folder / f"cv_{stances}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    log(table(report))
    r = report["reference_claim_source_only"]
    log(
        f"{'claim source only':22s} {r.get('auc') or 0:6.3f} {'(sees no vote)':>15s} "
        f"{r.get('accuracy', 0):6.3f} {r.get('macro_f1', 0):6.3f} {r.get('brier', 0):6.3f}"
    )
    return report


def _rows(path: Path) -> list[list[str]]:
    """CSV with a header (Zheng et al.), or tab-separated without one (Get-Another-Label)."""
    with path.open(encoding="utf-8") as f:
        if path.suffix == ".csv":
            return [list(r.values()) for r in csv.DictReader(f)]
        return [[c.strip() for c in line.split("\t")] for line in f if line.strip()]


def load_crowd(answers: Path, truth_file: Path, positive: str = "1"
               ) -> tuple[dict[str, int], dict[str, list[dict]]]:  # fmt: skip
    """Truth for the gold items, and votes on every item (unlabelled items still teach the
    unsupervised part about the workers). CSV rows are question, worker, answer;
    tab-separated rows are worker, item, label. `positive` is the label (or comma-separated
    labels) that means true."""
    pos = {x.strip().lower() for x in positive.split(",")}
    with answers.open(encoding="utf-8") as f:
        snow = f.readline().startswith("!amt_annotation_ids")
    if snow:  # Snow et al. 2008 standardized: annotation, worker, item, response, gold
        rows = _rows(answers)[1:]
        truth = {r[2]: int(r[4].lower() in pos) for r in rows}
        votes: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            votes[r[2]].append({"outlet": r[1], "vote": 1.0 if r[3].lower() in pos else -1.0,
                                "weight": 1.0, "conf": 1.0, "title": ""})  # fmt: skip
        return truth, dict(votes)
    truth = {r[0]: int(r[1].strip().lower() in pos) for r in _rows(truth_file)
             if len(r) >= 2 and r[1]}  # fmt: skip
    votes: dict[str, list[dict]] = defaultdict(list)
    for r in _rows(answers):
        if len(r) < 3 or not r[2]:
            continue
        item, worker = (r[0], r[1]) if answers.suffix == ".csv" else (r[1], r[0])
        v = 1.0 if r[2].strip().lower() in pos else -1.0
        votes[item].append({"outlet": worker, "vote": v, "weight": 1.0, "conf": 1.0,
                            "title": ""})  # fmt: skip
    return truth, dict(votes)


def benchmark(answers: Path, truth_file: Path, *, k: int = 5, positive: str = "1",
              log: Callable[[str], None] = print) -> dict:  # fmt: skip
    """Each fold in turn is scored with the other folds' truth known (80% supervision), and
    again with only one other fold known (20%), the sparse case."""
    truth, votes = load_crowd(answers, truth_file, positive)
    truth = {g: t for g, t in truth.items() if votes.get(g)}
    claims = sorted(set(votes) | set(truth))
    parts = folds(list(truth), k)
    base = {n: VARIANTS[n] for n in METHODS}  # carcux_eb: tried, not adopted (protocol)
    workers = {v["outlet"] for vs in votes.values() for v in vs}
    report = {"items": len(claims), "gold_items": len(truth), "workers": len(workers),
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


BUDGETS = (1, 2, 3, 5, 0)  # answers kept per item; 0 = all


def sparsity(answers: Path, truth_file: Path, *, positive: str = "1", seeds: int = 3,
             k: int = 5, log: Callable[[str], None] = print) -> dict:  # fmt: skip
    """The methods as each item's answers are randomly cut to a budget (seed-averaged)."""
    truth, votes = load_crowd(answers, truth_file, positive)
    truth = {g: t for g, t in truth.items() if votes.get(g)}
    claims = sorted(set(votes) | set(truth))
    parts = folds(list(truth), k)
    base = {n: VARIANTS[n] for n in METHODS}
    keys = ("auc", "accuracy", "brier", "ece", "acc_at_80pct")
    out: dict[str, dict] = {}
    for budget in BUDGETS:
        sums: dict[str, dict[str, float]] = {n: dict.fromkeys(keys, 0.0) for n in base}
        for seed in range(seeds):
            rng = random.Random(SEED + seed)  # noqa: S311 - reproducible subsampling
            cut = {g: (rng.sample(vs, budget) if budget and len(vs) > budget else list(vs))
                   for g, vs in votes.items()}  # fmt: skip
            rep = _pooled(truth, cut, claims, parts, base, ci=False)
            for n in base:
                for key in keys:
                    sums[n][key] += (rep[n]["with_votes"].get(key) or 0.0) / seeds
        out[str(budget or "all")] = sums
    lines = [f"{'answers/item':>12s} {'method':12s} {'AUC':>6s} {'acc':>6s} {'Brier':>6s} "
             f"{'ECE':>6s} {'acc@80':>6s}"]  # fmt: skip
    for budget, ms in out.items():
        for n, m in ms.items():
            lines.append(f"{budget:>12s} {n:12s} {m['auc']:6.3f} {m['accuracy']:6.3f} "
                         f"{m['brier']:6.3f} {m['ece']:6.3f} {m['acc_at_80pct']:6.3f}")  # fmt: skip
    log("\n".join(lines))
    return {"items": len(truth), "seeds": seeds, "budgets": out}


def table(report: dict) -> str:
    head = f"{'method':22s} {'AUC':>6s} {'95% CI':>15s} {'acc':>6s} {'F1':>6s} {'Brier':>6s}"
    lines = [head + f" {'ECE':>6s} {'acc@80':>6s}"]

    def row(name, w, ci_s=""):
        auc = w.get("auc")
        auc_s = "" if auc is None else f"{auc:.3f}"
        return (f"{name:22s} {auc_s:>6s} {ci_s:>15s} {w.get('accuracy', 0):6.3f} "
                f"{w.get('macro_f1', 0):6.3f} {w.get('brier', 0):6.3f} "
                f"{w.get('ece', 0):6.3f} {w.get('acc_at_80pct', 0):6.3f}")  # fmt: skip

    for name, m in report["methods"].items():
        ci = m["with_votes"].get("auc_95")
        lines.append(row(name, m["with_votes"], f"[{ci[0]:.3f}, {ci[1]:.3f}]" if ci else ""))
    for name, m in report.get("methods_20pct_known", {}).items():
        lines.append(row(name + " (20% known)", m))
    return "\n".join(lines)
