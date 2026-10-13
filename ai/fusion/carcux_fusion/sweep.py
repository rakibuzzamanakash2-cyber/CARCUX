"""RQ4: how fast does each method degrade as contamination rises from 0 to 60 %?

    python -m carcux_fusion.sweep [--levels 0 0.1 ... 0.6] [--seeds 3] [--events 120]
        [--json sweep.json]

For each level and seed, a simulated dataset is generated (same seed across levels, so
the clean part is identical and only the injected share changes), then evaluated with
`evaluate.run`. Reported: mean and spread over seeds of Brier score and accuracy at
T+6h and final, per method, on the clean events (the same situations at every level:
how much does contamination hurt judging them?) and on all events (including the
injected rumours).
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

from carcux_fusion import evaluate, simulate
from carcux_fusion.data import load

LEVELS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]


def run(levels=LEVELS, seeds: int = 3, events: int = 120, folds: int = 5, log=print) -> dict:
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for c in levels:
            for s in range(1, seeds + 1):
                out = Path(tmp) / f"c{c}-s{s}"
                simulate.generate(out, events=events, contamination=c, seed=s)
                r = evaluate.run(load(out), k=folds, seed=0)
                rows.append({"contamination": c, "seed": s, "result": r})
                log(
                    f"contamination {c:.1f} seed {s}: {r['events']} events, "
                    f"{r['observations']} observations"
                )
    return summarise(rows)


def summarise(rows: list[dict]) -> dict:
    out: dict = {"levels": sorted({r["contamination"] for r in rows}), "checkpoints": {}}
    for cp, key in (
        ("T+6h", "clean_events"),
        ("final", "clean_events"),
        ("T+6h", "methods"),
        ("final", "methods"),
    ):
        table: dict = {}
        for r in rows:
            block = r["result"]["checkpoints"][cp][key] or r["result"]["checkpoints"][cp]["methods"]
            for name, s in block.items():
                cell = table.setdefault(name, {}).setdefault(r["contamination"], [])
                cell.append(s)
        label = f"{cp}, {'clean events' if key == 'clean_events' else 'all events'}"
        out["checkpoints"][label] = {
            name: {
                str(c): {
                    k: {
                        "mean": float(np.mean([x[k] for x in v])),
                        "sd": float(np.std([x[k] for x in v])),
                    }
                    for k in ("brier", "accuracy")
                }
                for c, v in by_level.items()
            }
            for name, by_level in table.items()
        }
    out["detection_f1"] = {
        str(c): float(
            np.mean([r["result"]["detection"]["f1"] for r in rows if r["contamination"] == c])
        )
        for c in out["levels"]
    }
    return out


def table(summary: dict, metric: str = "brier") -> str:
    levels = summary["levels"]
    lines = []
    for cp, block in summary["checkpoints"].items():
        head = f"{metric}, {cp:<24}" + "".join(f"{f'{c:.0%}':>9}" for c in levels)
        lines += [head, "-" * len(head)]
        for name, by_level in block.items():
            cells = "".join(f"{by_level[str(c)][metric]['mean']:>9.3f}" for c in levels)
            lines.append(f"{name:<34}{cells}")
        lines.append("")
    det = "".join(f"{summary['detection_f1'][str(c)]:>9.3f}" for c in levels)
    lines.append(f"{'copy detection F1':<34}{det}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m carcux_fusion.sweep")
    parser.add_argument("--levels", type=float, nargs="+", default=LEVELS)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--events", type=int, default=120)
    parser.add_argument("--json")
    args = parser.parse_args(argv)
    summary = run(args.levels, args.seeds, args.events)
    print()
    print(table(summary, "brier"))
    print()
    print(table(summary, "accuracy"))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
