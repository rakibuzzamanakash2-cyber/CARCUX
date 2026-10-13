"""Evaluate correlation methods on a CARCUX-BD dataset, with grouped cross-validation.

    python -m carcux_correlation.evaluate DATASET_DIR [--folds 5] [--seed 0] [--json out.json]

Folds are grouped by root event, so no event is split between training and testing;
within a fold, scorers and thresholds are fitted on the training events only, then the
test observations are clustered as a stream (in time order) and scored. Results are
mean and standard deviation over folds.
"""

import argparse
import json
import sys
from dataclasses import dataclass, field

import numpy as np

from carcux_correlation import features as F
from carcux_correlation import models
from carcux_correlation.data import Dataset, load
from carcux_correlation.metrics import score

REPORTED = ["pair_precision", "pair_recall", "pair_f1", "bcubed_f1", "ari"]


@dataclass
class MethodResult:
    name: str
    folds: list[dict] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        out = {}
        for key in REPORTED + ["clusters", "gold_groups"]:
            values = [f[key] for f in self.folds]
            out[key] = {
                "mean": float(np.mean(values)) if values else None,
                "sd": float(np.std(values)) if values else None,
            }
        out["folds"] = len(self.folds)
        out["skipped_folds"] = self.skipped
        return out


def grouped_folds(obs, groups: list[str], k: int, seed: int):
    """k folds of whole events: groups shuffled with the seed, dealt out in turn.
    Each fold's items are returned in time order (the order a stream sees them)."""
    names = sorted(set(groups))
    np.random.default_rng(seed).shuffle(names)
    fold_of = {g: n % k for n, g in enumerate(names)}
    by_time = sorted(range(len(obs)), key=lambda i: (obs[i].time, obs[i].obs_id))
    for f in range(k):
        test = [i for i in by_time if fold_of[groups[i]] == f]
        train = [i for i in by_time if fold_of[groups[i]] != f]
        yield train, test


def run(
    data: Dataset,
    *,
    folds: int = 5,
    seed: int = 0,
    linkage: str = "average",
    method_list: list[models.Scorer] | None = None,
) -> dict:
    obs = data.observations
    groups = [o.primary for o in obs]
    n_groups = len(set(groups))
    if n_groups < 2:
        raise ValueError("Need at least two events to cross-validate")
    k = min(folds, n_groups)
    feats = F.matrix(obs)
    method_list = method_list or models.methods()
    results = {m.name: MethodResult(m.name) for m in method_list}

    for fold, (train, test) in enumerate(grouped_folds(obs, groups, k, seed)):
        gold_train = [obs[i].events for i in train]
        gold_test = [obs[i].events for i in test]
        primary_test = [obs[i].primary for i in test]
        for method in method_list:
            try:
                method.fit(obs, feats, train)
            except ValueError as exc:
                results[method.name].skipped.append(f"fold {fold}: {exc}")
                continue
            threshold = models.tune_threshold(method.scores(obs, feats, train), gold_train, linkage)
            pred = models.cluster(method.scores(obs, feats, test), threshold, linkage)
            s = score(pred, gold_test, primary_test).as_dict()
            s["threshold"] = threshold
            results[method.name].folds.append(s)

    return {
        "dataset": data.name,
        "observations": len(obs),
        "unannotated_left_out": data.unannotated,
        "events": n_groups,
        "folds": k,
        "seed": seed,
        "linkage": linkage,
        "methods": {name: r.summary() for name, r in results.items()},
    }


def table(result: dict) -> str:
    head = f"{'method':<13}" + "".join(f"{k:>16}" for k in REPORTED)
    lines = [
        f"{result['dataset']}: {result['observations']} observations, {result['events']} "
        f"events, {result['folds']}-fold grouped CV (seed {result['seed']})",
        head,
        "-" * len(head),
    ]
    for name, s in result["methods"].items():
        if s["folds"] == 0:
            lines.append(f"{name:<13}  not run: {'; '.join(s['skipped'])[:80]}")
            continue
        cells = "".join(f"{s[k]['mean']:>9.3f} ±{s[k]['sd']:.3f}" for k in REPORTED)
        lines.append(f"{name:<13}{cells}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m carcux_correlation.evaluate")
    parser.add_argument("dataset", help="directory with the CARCUX-BD JSON Lines files")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--linkage", choices=["average", "max"], default="average")
    parser.add_argument("--json", help="also write the full results here")
    args = parser.parse_args(argv)
    data = load(args.dataset)
    try:
        result = run(data, folds=args.folds, seed=args.seed, linkage=args.linkage)
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
