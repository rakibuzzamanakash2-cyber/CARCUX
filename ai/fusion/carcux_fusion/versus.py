"""The proposed method against chosen rivals, pooled over seeds, at every contamination
level: is the difference real?

    python -m carcux_fusion.versus [--seeds 5] [--events 120] [--json versus.json]

For each level and seed a simulated set is generated and evaluated (5-fold CV, as in
`evaluate`). Each method's squared errors on held-out events are pooled over seeds, and
the difference from the proposed method gets a paired bootstrap over events (95 %
interval, p-value), at T+6h and at the final checkpoint.
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

from carcux_fusion import evaluate, simulate
from carcux_fusion.data import load
from carcux_fusion.sweep import LEVELS

RIVALS = [
    "socialsensing",
    "socialsensing-dep",
    "socialsensing-dep-nosilence",
    "socialsensing-dep-nosilence-sup",
    "truthfinder-dep",
    "reliability-dedup",
]
CHECKPOINTS = ("T+6h", "final")


def run(levels=LEVELS, seeds: int = 5, events: int = 120, rivals=RIVALS, log=print) -> dict:
    out: dict = {"seeds": seeds, "events_per_set": events, "proposed": evaluate.PROPOSED}
    with tempfile.TemporaryDirectory() as tmp:
        for c in levels:
            loss: dict[tuple[str, str], list[float]] = {}
            for s in range(1, seeds + 1):
                where = Path(tmp) / f"c{c}-s{s}"
                simulate.generate(where, events=events, contamination=c, seed=s)
                data, keep = load(where), {}
                evaluate.run(data, k=5, seed=0, keep=keep)
                for cp in CHECKPOINTS:
                    for m, preds in keep["predictions"][cp].items():
                        for e, p in preds.items():
                            y = int(data.events[e].occurred)
                            loss.setdefault((cp, m), []).append((p - y) ** 2)
            out[str(c)] = {}
            for cp in CHECKPOINTS:
                base = loss[(cp, evaluate.PROPOSED)]
                row = {"n": len(base), evaluate.PROPOSED: {"brier": float(np.mean(base))}}
                for m in rivals:
                    row[m] = {
                        "brier": float(np.mean(loss[(cp, m)])),
                        **evaluate.paired_bootstrap(loss[(cp, m)], base, seed=0),
                    }
                out[str(c)][cp] = row
            log(f"contamination {c:.1f} done")
    return out


def table(result: dict, checkpoint: str = "final") -> str:
    proposed = result["proposed"]
    rivals = [k for k in next(iter(v for k, v in result.items() if k[0].isdigit()))[checkpoint]
              if k not in ("n", proposed)]  # fmt: skip
    lines = [f"Brier at {checkpoint}, {result['seeds']} seeds pooled; difference = proposed "
             "minus rival (negative favours the proposed method)", ""]  # fmt: skip
    for m in rivals:
        lines.append(f"{proposed} vs {m}")
        for c, block in result.items():
            if not c[0].isdigit():
                continue
            r = block[checkpoint]
            v = r[m]
            lines.append(
                f"  {float(c):>4.0%}  {r[proposed]['brier']:.3f} vs {v['brier']:.3f}  "
                f"{v['diff']:+.3f} [{v['ci_low']:+.3f}, {v['ci_high']:+.3f}]  p={v['p_value']:.3f}"
            )
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m carcux_fusion.versus")
    parser.add_argument("--levels", type=float, nargs="+", default=LEVELS)
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--events", type=int, default=120)
    parser.add_argument("--json")
    args = parser.parse_args(argv)
    result = run(args.levels, args.seeds, args.events)
    for cp in CHECKPOINTS:
        print(table(result, cp))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
