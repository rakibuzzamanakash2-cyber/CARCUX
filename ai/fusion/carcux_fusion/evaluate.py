"""Evaluate fusion methods on a CARCUX-BD dataset: did the event really happen?

    python -m carcux_fusion.evaluate DATASET_DIR [--folds 5] [--seed 0] [--json out.json]

- Events are split into folds (seeded); methods learn (source reliability, copy
  threshold, calibration) on the other folds' events only.
- Each event is judged at T+1h, T+6h, T+24h and final (7 days) after its first
  observation, from the evidence published by then.
- Scores (Brier, log loss, ECE, accuracy, AUC) are computed over all events' held-out
  predictions; differences in Brier between the proposed method and each other method
  get a paired bootstrap over events (95 % interval, p-value).
- Copy detection is scored on held-out events against the gold dependences.
"""

import argparse
import json
import sys
from datetime import timedelta

import numpy as np

from carcux_fusion import dependence, metrics
from carcux_fusion import methods as M
from carcux_fusion.data import Dataset, load

CHECKPOINTS = [("T+1h", 1), ("T+6h", 6), ("T+24h", 24), ("final", 24 * 7)]
PROPOSED = "reliability-dep"
INNER_FOLDS = 5
REPORTED = ["brier", "ece", "accuracy", "auc"]


def folds(event_ids: list[str], k: int, seed: int) -> list[list[str]]:
    ids = sorted(event_ids)
    np.random.default_rng(seed).shuffle(ids)
    return [ids[f::k] for f in range(k)]


def paired_bootstrap(loss_a, loss_b, *, resamples: int = 2000, seed: int = 0) -> dict:
    """Mean loss of b minus a, resampling events. Negative favours b."""
    a, b = np.asarray(loss_a), np.asarray(loss_b)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(a), size=(resamples, len(a)))
    diff = (b[idx] - a[idx]).mean(axis=1)
    low, high = np.quantile(diff, [0.025, 0.975])
    p = min(1.0, 2 * min(np.mean(diff <= 0), np.mean(diff >= 0)))
    return {
        "diff": float((b - a).mean()),
        "ci_low": float(low),
        "ci_high": float(high),
        "p_value": float(p),
    }


def run(
    data: Dataset,
    *,
    k: int = 5,
    seed: int = 0,
    method_list=None,
    keep: dict | None = None,
    checkpoints=None,
    parts: list[list[str]] | None = None,
    copy_threshold: float | None = None,
    test_folds: list[int] | None = None,
) -> dict:
    """`parts`: explicit folds (for example one per crisis) instead of `k` seeded ones.
    `copy_threshold`: a fixed copy-detection threshold, for data without gold copies
    to tune one on. `test_folds`: only these folds are judged (for a held-out test set:
    the other folds are training data only); scores cover their events alone."""
    events = [eid for eid, e in data.events.items() if e.evidence]
    if parts is not None:
        keep_ids = set(events)
        parts = [[e for e in p if e in keep_ids] for p in parts]
        parts = [p for p in parts if p]
        k = len(parts)
    if len(events) < k or len({data.events[e].occurred for e in events}) < 2:
        raise ValueError("need events that happened and events that did not, at least one per fold")
    parts = parts if parts is not None else folds(events, k, seed)
    tested = list(range(len(parts))) if test_folds is None else list(test_folds)
    scored = [e for f in tested for e in parts[f]]
    detector = dependence.Detector(data)
    first = {eid: data.first_seen(data.events[eid]) for eid in events}
    truth = {eid: int(data.events[eid].occurred) for eid in events}
    method_list = method_list or M.methods()

    detected_by_fold, detection = [], []
    for f, test in enumerate(parts):
        train = [e for p, part in enumerate(parts) if p != f for e in part]
        threshold = copy_threshold if copy_threshold is not None else detector.tune(train)
        detected_by_fold.append(detector.detect(events, threshold))
        detection.append(
            {"threshold": threshold, **dependence.score(detected_by_fold[-1], data, test)}
        )

    result = {
        "dataset": data.name,
        "events": len(events),
        "happened": sum(truth.values()),
        "observations": sum(len(data.events[e].evidence) for e in events),
        "gold_copies": len(data.dependences),
        "folds": k,
        "seed": seed,
        "judged": len(scored),
        "judged_happened": sum(truth[e] for e in scored),
        "detection": _mean_detection(detection),
        "checkpoints": {},
    }
    for name, hours in checkpoints or CHECKPOINTS:
        cutoffs = {eid: first[eid] + timedelta(hours=hours) for eid in events}
        preds = {m.name: {} for m in method_list}
        raws: dict[str, list[dict]] = {m.name: [] for m in method_list}
        for f, test in enumerate(parts):
            if f not in tested:
                continue
            train = [e for p, part in enumerate(parts) if p != f for e in part]
            for m in method_list:
                links = {} if m.ignore_structure else data.structure
                deps = {
                    "gold": {**links, **data.dependences},
                    "detected": {**links, **detected_by_fold[f]},
                }.get(m.uses_deps or "", {})
                calib = _out_of_fold(m, data, train, events, cutoffs, deps, seed)
                m.fit(data, train, cutoffs, deps)
                raw = m.raw(data, events, cutoffs, deps)
                raws[m.name].append(raw)
                calib = calib or raw
                cal = M.Platt().fit([calib[e] for e in train], [truth[e] for e in train])
                for e, p in zip(test, cal.predict([raw[e] for e in test]), strict=True):
                    preds[m.name][e] = float(p)
        y = [truth[e] for e in scored]
        table = {}
        for m in method_list:
            p = [preds[m.name][e] for e in scored]
            table[m.name] = metrics.score(p, y).as_dict()
            table[m.name]["reliability"] = metrics.reliability(np.array(p), np.array(y))
        clean = [e for e in scored if not data.events[e].injected]
        clean_table = None
        if len(clean) < len(scored) and len({truth[e] for e in clean}) == 2:
            yc = [truth[e] for e in clean]
            clean_table = {
                m.name: metrics.score([preds[m.name][e] for e in clean], yc).as_dict()
                for m in method_list
            }
        loss = {m: [(preds[m][e] - truth[e]) ** 2 for e in scored] for m in preds}
        comparisons = {
            other: paired_bootstrap(loss[other], loss[PROPOSED], seed=seed)
            for other in preds
            if other != PROPOSED and PROPOSED in preds
        }
        if keep is not None:
            keep.setdefault("predictions", {})[name] = preds
            keep.setdefault("raw", {})[name] = raws  # method -> per fold -> event -> score
        result["checkpoints"][name] = {
            "methods": table,
            "brier_vs_proposed": comparisons,
            # Simulated contamination only: the events that were not injected, so the
            # same real-world situations can be compared across contamination levels.
            "clean_events": clean_table,
        }
    if keep is not None:
        keep.update(folds=parts, detected=detected_by_fold, events=events)
    return result


def _out_of_fold(m, data, train, events, cutoffs, deps, seed, k: int = INNER_FOLDS):
    """For a method that learns from outcomes: each training event's score from a model
    fitted without it (inner folds), so the calibration is fitted on scores like the
    ones it will see on test events. Fitting it on in-sample scores makes it trust them
    too much wherever the method can memorise its training events, which happens when
    most sources speak about one event only (the first real-data run). None for
    unsupervised methods, whose in-sample scores are already honest."""
    if not m.supervised or len(train) < k:
        return None
    out: dict[str, object] = {}
    for inner in folds(train, k, seed):
        rest = [e for e in train if e not in set(inner)]
        if len({data.events[e].occurred for e in rest}) < 2:
            continue
        m.fit(data, rest, cutoffs, deps)
        raw = m.raw(data, events, cutoffs, deps)
        out.update({e: raw[e] for e in inner})
    return out if len(out) == len(train) else None


def _mean_detection(rows: list[dict]) -> dict:
    keys = ["precision", "recall", "f1", "threshold"]
    out = {k: float(np.mean([r[k] for r in rows])) for k in keys}
    origin = [r["origin_in_cascade"] for r in rows if r["origin_in_cascade"] is not None]
    out["origin_in_cascade"] = float(np.mean(origin)) if origin else None
    return out


def table(result: dict) -> str:
    d = result["detection"]
    lines = [
        f"{result['dataset']}: {result['events']} events ({result['happened']} happened), "
        f"{result['observations']} observations, {result['gold_copies']} gold copies, "
        f"{result['folds']}-fold CV (seed {result['seed']})",
        f"copy detection on held-out events: precision {d['precision']:.3f}, recall "
        f"{d['recall']:.3f}, F1 {d['f1']:.3f}, origin in the right cascade "
        f"{(d['origin_in_cascade'] or 0):.3f}",
    ]
    for cp, block in result["checkpoints"].items():
        lines.append("")
        head = f"{cp:<20}" + "".join(f"{k:>11}" for k in REPORTED) + f"{'Brier vs ' + PROPOSED:>40}"
        lines += [head, "-" * len(head)]
        for name, s in block["methods"].items():
            cells = "".join(
                f"{s[k]:>11.3f}" if s[k] is not None else f"{'-':>11}" for k in REPORTED
            )
            c = block["brier_vs_proposed"].get(name)
            cmp = (
                f"{c['diff']:+.3f} [{c['ci_low']:+.3f}, {c['ci_high']:+.3f}] p={c['p_value']:.3f}"
                if c
                else "(proposed)"
            )
            lines.append(f"{name:<20}{cells}{cmp:>40}")
    lines.append("")
    lines.append(f"Brier vs {PROPOSED}: its Brier minus the other method's; negative favours it.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m carcux_fusion.evaluate")
    parser.add_argument("dataset")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--json")
    args = parser.parse_args(argv)
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
