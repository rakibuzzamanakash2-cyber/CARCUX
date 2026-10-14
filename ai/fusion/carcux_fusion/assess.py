"""The six-label assessment, and whether explicit conflict detection helps (RQ3).

    python -m carcux_fusion.assess DATASET_DIR [--folds 5] [--seed 0] [--json out.json]
    python -m carcux_fusion.assess --simulate [--levels 0 0.3 0.6] [--seeds 3]

At each checkpoint an event gets one of the dataset's labels:

- **verified**: the probability it happened (from `evaluate`) is at least `high`, and no
  detail is in dispute;
- **partially_verified**: at least `high`, but credible reports disagree on a detail;
- **refuted**: at most `low`;
- **conflicting**: in between, with credible first-hand reports on both sides;
- **unverified**: in between otherwise;
- **insufficient_evidence**: nothing in view.

`high` and `low` are tuned on the training folds (best macro-F1 against gold labels).
Variants, all on the proposed model's probabilities:

- `probability only`: no conflict modelling (a disputed event is called verified);
- `conflicts`: disputes detected from the claimed values (proposed);
- `conflicts (annotated)`: disputes from the annotators' `conflicts` (upper bound);
- and, for reference, `majority, probability only` on majority-vote probabilities.

Also reported: how often an event is called **verified when it should not be** (the
costly error), and how often each strategy gets the details themselves right (the
first report, the most common value, one per cascade, one per cascade weighted by
reliability).
"""

import argparse
import json
import sys
import tempfile
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import numpy as np
from sklearn.metrics import f1_score

from carcux_fusion import conflict, evaluate, simulate
from carcux_fusion import methods as M
from carcux_fusion.data import Dataset, load

LABELS = [
    "verified",
    "partially_verified",
    "conflicting",
    "unverified",
    "refuted",
    "insufficient_evidence",
]
HIGH = np.round(np.arange(0.5, 0.96, 0.05), 2)
LOW = np.round(np.arange(0.05, 0.46, 0.05), 2)
VARIANTS = ["probability only", "conflicts", "conflicts (annotated)", "majority, probability only"]
STRATEGIES = ["first", "majority", "independent", "weighted"]


def label(p: float, seen: int, support: int, deny: int, disputed: bool, high, low) -> str:
    if seen == 0:
        return "insufficient_evidence"
    if p >= high:
        return "partially_verified" if disputed else "verified"
    if p <= low:
        return "refuted"
    return "conflicting" if support and deny else "unverified"


def _tune(rows: list[dict], key: str) -> tuple[float, float]:
    """Thresholds with the best macro-F1 on these (training) rows."""
    best, best_f = (0.8, 0.2), -1.0
    gold = [r["gold"] for r in rows]
    for hi in HIGH:
        for lo in LOW:
            if lo >= hi:
                continue
            pred = [label(r["p"], r["seen"], r["support"], r["deny"], r[key], hi, lo) for r in rows]
            f = f1_score(gold, pred, labels=LABELS, average="macro", zero_division=0)
            if f > best_f + 1e-12:
                best, best_f = (float(hi), float(lo)), f
    return best


def run(data: Dataset, *, k: int = 5, seed: int = 0, keep: dict | None = None) -> dict:
    """`keep`, if given, receives per checkpoint the rows and each variant's labels."""
    keep = {} if keep is None else keep
    proposed = M.Reliability("detected")
    majority = M.Majority()
    evaluate.run(data, k=k, seed=seed, method_list=[majority, proposed], keep=keep)
    parts, events = keep["folds"], keep["events"]
    fold_of = {e: f for f, part in enumerate(parts) for e in part}
    first = {e: data.first_seen(data.events[e]) for e in events}
    result: dict = {"dataset": data.name, "events": len(events), "checkpoints": {}}

    for cp, hours in evaluate.CHECKPOINTS:
        preds = keep["predictions"][cp]
        rows: dict[str, dict] = {}
        value_hits: dict[str, list[int]] = defaultdict(list)
        per_detail: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
        for f, test in enumerate(parts):
            train = [e for p, part in enumerate(parts) if p != f for e in part]
            deps = keep["detected"][f]
            cut = {e: first[e] + timedelta(hours=hours) for e in events}
            model = M.Reliability("detected").fit(data, train, cut, deps)
            rate = model.rate
            for e in test:
                event = data.events[e]
                gold = event.gold_labels.get(cp)
                vs = M.independent(M.votes(data, event, cut[e], deps))
                credible = [v for v in vs if rate(v.source_id) >= conflict.CREDIBLE_RATE]
                cs = conflict.claims(data, event, cut[e], deps, rate)
                rows[e] = {
                    "gold": gold,
                    "p": preds[proposed.name][e],
                    "p_majority": preds[majority.name][e],
                    "seen": len(vs),
                    "support": sum(v.vote > 0 for v in credible),
                    "deny": sum(v.vote < 0 for v in credible),
                    "detected": any(conflict.disputed(c) for c in cs.values()),
                    "annotated": any(conflict.disputed_annotated(c) for c in cs.values()),
                    "none": False,
                }
                if event.occurred and event.facts:
                    for detail, est in conflict.estimates(data, event, cut[e], deps, rate).items():
                        truth = event.facts.get(detail)
                        if truth is None:
                            continue
                        for s in STRATEGIES:
                            # No estimate (e.g. a mis-detected copy hid the claim) is a miss.
                            hit = int(est[s] is not None and conflict.agrees(detail, est[s], truth))
                            value_hits[s].append(hit)
                            per_detail[detail][s].append(hit)
        scored = [e for e in events if rows[e]["gold"]]
        table = {}
        for variant in VARIANTS:
            key = {
                "probability only": "none",
                "conflicts": "detected",
                "conflicts (annotated)": "annotated",
                "majority, probability only": "none",
            }[variant]
            p_key = "p_majority" if variant.startswith("majority") else "p"
            pred, gold, labelled = [], [], {}
            for f, test in enumerate(parts):
                train_rows = [{**rows[e], "p": rows[e][p_key]} for e in scored if fold_of[e] != f]
                hi, lo = _tune(train_rows, key)
                for e in test:
                    if not rows[e]["gold"]:
                        continue
                    r = rows[e]
                    labelled[e] = label(
                        r[p_key], r["seen"], r["support"], r["deny"], r[key], hi, lo
                    )
                    pred.append(labelled[e])
                    gold.append(r["gold"])
            table[variant] = _label_scores(pred, gold)
            keep.setdefault("labels", {}).setdefault(cp, {})[variant] = labelled
        keep.setdefault("rows", {})[cp] = rows
        result["checkpoints"][cp] = {
            "assessment": table,
            "details": {s: (float(np.mean(v)) if v else None) for s, v in value_hits.items()},
            "details_by_kind": {
                d: {s: float(np.mean(v)) for s, v in by.items()} for d, by in per_detail.items()
            },
            "gold_labels": {lab: sum(rows[e]["gold"] == lab for e in scored) for lab in LABELS},
        }
    return result


def _label_scores(pred: list[str], gold: list[str]) -> dict:
    n = len(gold)
    wrongly_verified = sum(
        p == "verified" and g != "verified" for p, g in zip(pred, gold, strict=True)
    )
    missed_dispute = sum(
        p == "verified" and g == "partially_verified" for p, g in zip(pred, gold, strict=True)
    )
    return {
        "accuracy": float(np.mean([p == g for p, g in zip(pred, gold, strict=True)]))
        if n
        else None,
        "macro_f1": float(f1_score(gold, pred, labels=LABELS, average="macro", zero_division=0)),
        "wrongly_verified": wrongly_verified / n if n else None,
        "missed_disputes": missed_dispute,
        "partially_verified_f1": float(
            f1_score(gold, pred, labels=["partially_verified"], average="macro", zero_division=0)
        ),
    }


def table(result: dict) -> str:
    lines = [f"{result['dataset']}: {result['events']} events"]
    for cp, block in result["checkpoints"].items():
        lines.append("")
        lines.append(
            f"{cp}  gold: " + ", ".join(f"{k} {v}" for k, v in block["gold_labels"].items() if v)
        )
        head = f"{'':<28}{'accuracy':>10}{'macro-F1':>10}{'partly-F1':>11}{'wrongly verified':>18}"
        lines += [head, "-" * len(head)]
        for name, s in block["assessment"].items():
            lines.append(
                f"{name:<28}{s['accuracy']:>10.3f}{s['macro_f1']:>10.3f}"
                f"{s['partially_verified_f1']:>11.3f}{s['wrongly_verified']:>18.3f}"
            )
        d = block["details"]
        if d:
            lines.append(
                "details right: " + ", ".join(f"{s} {d[s]:.3f}" for s in STRATEGIES if s in d)
            )
    return "\n".join(lines)


def sweep(levels, seeds: int, events: int = 120, log=print) -> dict:
    out: dict = {"levels": list(levels), "runs": []}
    with tempfile.TemporaryDirectory() as tmp:
        for c in levels:
            for s in range(1, seeds + 1):
                path = Path(tmp) / f"c{c}-s{s}"
                simulate.generate(path, events=events, contamination=c, seed=s)
                r = run(load(path))
                out["runs"].append({"contamination": c, "seed": s, "result": r})
                log(f"contamination {c:.1f} seed {s} done")
    return out


def _mean(summary: dict, c: float, pick) -> float:
    return float(np.mean([pick(r["result"]) for r in summary["runs"] if r["contamination"] == c]))


def sweep_table(summary: dict, cp: str = "final") -> str:
    levels = summary["levels"]
    lines = []
    for metric in ("macro_f1", "partially_verified_f1", "wrongly_verified"):
        head = f"{metric} at {cp:<14}" + "".join(f"{f'{c:.0%}':>9}" for c in levels)
        lines += [head, "-" * len(head)]
        for v in VARIANTS:

            def pick(r, v=v, m=metric):
                return r["checkpoints"][cp]["assessment"][v][m]

            cells = "".join(f"{_mean(summary, c, pick):>9.3f}" for c in levels)
            lines.append(f"{v:<30}{cells}")
        lines.append("")
    head = f"details right at {cp:<9}" + "".join(f"{f'{c:.0%}':>9}" for c in levels)
    lines += [head, "-" * len(head)]
    for s in STRATEGIES:
        cells = "".join(
            f"{_mean(summary, c, lambda r, s=s: r['checkpoints'][cp]['details'][s]):>9.3f}"
            for c in levels
        )
        lines.append(f"{s:<30}{cells}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m carcux_fusion.assess")
    parser.add_argument("dataset", nargs="?")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--simulate", action="store_true", help="sweep simulated sets instead")
    parser.add_argument("--levels", type=float, nargs="+", default=[0.0, 0.3, 0.6])
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--json")
    args = parser.parse_args(argv)
    if args.simulate:
        result = sweep(args.levels, args.seeds)
        print()
        for cp in ("T+6h", "final"):
            print(sweep_table(result, cp))
            print()
    else:
        if not args.dataset:
            parser.error("give a dataset folder, or --simulate")
        try:
            result = run(load(args.dataset), k=args.folds, seed=args.seed)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(table(result))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
