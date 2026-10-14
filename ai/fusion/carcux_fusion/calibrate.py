"""Are the probabilities honest, and do the six labels add anything (RQ5)?

    python -m carcux_fusion.calibrate DATASET_DIR [--folds 5] [--seed 0] [--json out.json]
    python -m carcux_fusion.calibrate --simulate [--levels 0 0.3 0.6] [--seeds 3]
        [--figures DIR] [--json out.json]

**Calibration.** When the system says "80 % likely", does it happen about 80 % of the
time? Each method's raw score is turned into a probability in several ways, all fitted
on the training folds only:

- `none`: the score read as log-odds as it stands (sigmoid of the score; for the
  two-channel model, of the two channels' sum): what the method claims by itself;
- `temperature`: one learned scale on that score, no shift;
- `platt`: a learned scale and shift (what `evaluate` uses everywhere);
- `isotonic`: a learned monotone step function (non-parametric);
- `platt-final`: Platt fitted on the training events' *final* evidence and used at
  every checkpoint (one calibrator for all times, as a deployment would most simply do);
- `platt-clean`: Platt fitted on training events that were not injected rumours (a
  calibrator fitted before a contamination wave; simulator only, equals `platt` otherwise).

Reported per method, calibrator and checkpoint: Brier, log loss, ECE, adaptive ECE,
bias (mean prediction minus how often events happened), and a paired bootstrap of Brier
against `platt`; plus reliability-diagram bins.

**Six labels vs one probability.** With the proposed model and conflict detection
(`assess`):

- per assigned label: how many events, their mean probability, and how often they
  really happened (do the labels mean what they say?);
- whether the signals behind the labels (credible reports on both sides, then also how
  many independent reports) predict occurrence beyond the probability itself: a
  logistic model on the probability alone vs ones that also see those signals, fitted
  on the training folds, scored on held-out events.

A detail in dispute is left out of that test: in the simulator only events that
happened have disputed details (a false event's reports repeat one invented story), so
it would predict occurrence by construction. For the same reason, events labelled
partially verified always happened on simulated data; real data must show whether
that holds.
"""

import argparse
import json
import math
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from carcux_fusion import assess, evaluate, metrics, simulate
from carcux_fusion import methods as M
from carcux_fusion.data import Dataset, load

CALIBRATORS = ["none", "temperature", "platt", "isotonic", "platt-final", "platt-clean"]
REFERENCE = "platt"
MIN_BIN = 5  # reliability-diagram bins with fewer events are not drawn
PROPOSED = evaluate.PROPOSED
SIGNALS = {
    "probability only": (),
    "+ both sides": ("both",),
    "+ both sides, report count": ("both", "count"),
}


def method_list() -> list[M.Method]:
    return [
        M.Majority(),
        M.TruthFinder(dependence=True),
        M.Reliability(None),
        M.Reliability("detected"),
    ]


# --- Calibrators -----------------------------------------------------------------------


def _total(scores) -> np.ndarray:
    """One number per event: the score, or the sum of a multi-channel score."""
    x = np.asarray(scores, dtype=float)
    return x if x.ndim == 1 else x.sum(axis=1)


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(z, -30, 30)))


def _constant(y: np.ndarray) -> Callable:
    base = float(y.mean()) if len(y) else 0.5
    return lambda s: np.full(len(s), base)


def fit(kind: str, scores, labels) -> Callable:
    """A function from scores to probabilities, fitted on (scores, labels)."""
    y = np.asarray(labels)
    if kind == "none":
        return lambda s: _sigmoid(_total(s))
    if len(set(y.tolist())) < 2:
        return _constant(y)
    if kind == "temperature":
        lr = LogisticRegression(C=100.0, fit_intercept=False).fit(_total(scores)[:, None], y)
        return lambda s: lr.predict_proba(_total(s)[:, None])[:, 1]
    platt = M.Platt().fit(scores, y.tolist())
    if kind == "platt":
        return platt.predict
    if kind == "isotonic":

        def line(s):  # Platt's linear score: one number per event, any number of channels
            return platt.model.decision_function(M._matrix(s))

        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(line(scores), y)
        return lambda s: iso.predict(line(s))
    raise ValueError(f"unknown calibrator {kind}")


# --- Calibration -----------------------------------------------------------------------


def _scores(p: list[float], y: list[int]) -> dict:
    out = metrics.score(p, y).as_dict()
    pa, ya = np.asarray(p, dtype=float), np.asarray(y, dtype=float)
    out["ece_adaptive"] = metrics.ece_adaptive(pa, ya)
    out["bias"] = float(pa.mean() - ya.mean())
    return out


def calibration(data: Dataset, *, k: int = 5, seed: int = 0) -> dict:
    keep: dict = {}
    ms = method_list()
    evaluate.run(data, k=k, seed=seed, method_list=ms, keep=keep)
    parts, events = keep["folds"], keep["events"]
    truth = {e: int(data.events[e].occurred) for e in events}
    out: dict = {"checkpoints": {}}
    for cp, _ in evaluate.CHECKPOINTS:
        preds: dict = {m.name: {c: {} for c in CALIBRATORS} for m in ms}
        for m in ms:
            for f, test in enumerate(parts):
                train = [e for p, part in enumerate(parts) if p != f for e in part]
                raw, final = keep["raw"][cp][m.name][f], keep["raw"]["final"][m.name][f]
                clean = [e for e in train if not data.events[e].injected] or train

                def fitted(kind, on, source):
                    return fit(kind, [source[e] for e in on], [truth[e] for e in on])

                cal = {
                    "none": fitted("none", train, raw),
                    "temperature": fitted("temperature", train, raw),
                    "platt": fitted("platt", train, raw),
                    "isotonic": fitted("isotonic", train, raw),
                    "platt-final": fitted("platt", train, final),
                    "platt-clean": fitted("platt", clean, raw),
                }
                x = [raw[e] for e in test]
                for c, fn in cal.items():
                    for e, p in zip(test, fn(x), strict=True):
                        preds[m.name][c][e] = float(p)
        y = [truth[e] for e in events]
        block: dict = {}
        for name, by_cal in preds.items():
            loss = {c: [(by_cal[c][e] - truth[e]) ** 2 for e in events] for c in CALIBRATORS}
            block[name] = {}
            for c in CALIBRATORS:
                p = [by_cal[c][e] for e in events]
                block[name][c] = {
                    **_scores(p, y),
                    "reliability": metrics.reliability(np.array(p), np.array(y)),
                    "brier_vs_platt": None
                    if c == REFERENCE
                    else evaluate.paired_bootstrap(loss[c], loss[REFERENCE], seed=seed),
                }
        out["checkpoints"][cp] = {
            "methods": block,
            # Kept for pooling across simulated runs (reliability diagrams).
            "predictions": {
                c: [preds[PROPOSED][c][e] for e in events] for c in ("none", "platt", "isotonic")
            },
            "truth": y,
        }
    return out


# --- Labels vs one probability ------------------------------------------------------------


def _features(row: dict, signals: tuple[str, ...]) -> list[float]:
    p = min(max(row["p"], 1e-4), 1 - 1e-4)
    x = [math.log(p / (1 - p))]
    if "both" in signals:  # credible first-hand reports on both sides (`conflicting`)
        x.append(float(bool(row["support"] and row["deny"])))
    if "count" in signals:  # how many independent reports (`insufficient_evidence` at 0)
        x += [float(row["seen"] == 0), math.log1p(row["seen"])]
    return x


def labels(data: Dataset, *, k: int = 5, seed: int = 0) -> dict:
    keep: dict = {}
    assess.run(data, k=k, seed=seed, keep=keep)
    parts = keep["folds"]
    out: dict = {"checkpoints": {}}
    for cp, _ in evaluate.CHECKPOINTS:
        rows, assigned = keep["rows"][cp], keep["labels"][cp]["conflicts"]
        happened = {e: int(data.events[e].occurred) for e in rows}
        by_label = {}
        for lab in assess.LABELS:
            es = [e for e, x in assigned.items() if x == lab]
            by_label[lab] = {
                "n": len(es),
                "mean_p": float(np.mean([rows[e]["p"] for e in es])) if es else None,
                "happened": float(np.mean([happened[e] for e in es])) if es else None,
            }
        preds: dict[str, dict[str, float]] = {s: {} for s in SIGNALS}
        for f, test in enumerate(parts):
            train = [e for p, part in enumerate(parts) if p != f for e in part]
            yt = np.array([happened[e] for e in train])
            for s, signals in SIGNALS.items():
                xt = np.array([_features(rows[e], signals) for e in train])
                xs = np.array([_features(rows[e], signals) for e in test])
                if len(set(yt.tolist())) < 2:
                    ps = np.full(len(test), yt.mean())
                else:
                    ps = LogisticRegression(C=100.0).fit(xt, yt).predict_proba(xs)[:, 1]
                preds[s].update({e: float(p) for e, p in zip(test, ps, strict=True)})
        events = sorted(rows)
        y = [happened[e] for e in events]
        loss = {s: [(preds[s][e] - happened[e]) ** 2 for e in events] for s in SIGNALS}
        out["checkpoints"][cp] = {
            "by_label": by_label,
            "occurrence": {s: _scores([preds[s][e] for e in events], y) for s in SIGNALS},
            # Brier of the probability alone minus with the signals; positive: signals help.
            "signals_vs_probability": {
                s: evaluate.paired_bootstrap(loss[s], loss["probability only"], seed=seed)
                for s in list(SIGNALS)[1:]
            },
        }
    return out


def run(data: Dataset, *, k: int = 5, seed: int = 0) -> dict:
    return {
        "dataset": data.name,
        "events": sum(1 for e in data.events.values() if e.evidence),
        "calibration": calibration(data, k=k, seed=seed),
        "labels": labels(data, k=k, seed=seed),
    }


# --- Reporting ---------------------------------------------------------------------------


def table(result: dict) -> str:
    lines = [f"{result['dataset']}: {result['events']} events"]
    for cp, block in result["calibration"]["checkpoints"].items():
        lines.append("")
        head = (
            f"{cp:<34}{'Brier':>8}{'log loss':>10}{'ECE':>8}{'ECE-a':>8}{'bias':>8}"
            f"{'Brier vs platt':>36}"
        )
        lines += [head, "-" * len(head)]
        for name, by_cal in block["methods"].items():
            for c, s in by_cal.items():
                b = s["brier_vs_platt"]
                cmp = (
                    f"{b['diff']:+.3f} [{b['ci_low']:+.3f}, {b['ci_high']:+.3f}] "
                    f"p={b['p_value']:.3f}"
                    if b
                    else "(reference)"
                )
                lines.append(
                    f"{name + ', ' + c:<34}{s['brier']:>8.3f}{s['log_loss']:>10.3f}"
                    f"{s['ece']:>8.3f}{s['ece_adaptive']:>8.3f}{s['bias']:>+8.3f}{cmp:>36}"
                )
    lines += ["", "Brier vs platt: platt's Brier minus the other's; negative favours platt."]
    for cp, block in result["labels"]["checkpoints"].items():
        lines += ["", f"{cp}: assigned label (proposed + conflicts)  n  mean p  happened"]
        for lab, s in block["by_label"].items():
            if s["n"]:
                lines.append(f"  {lab:<36}{s['n']:>3}{s['mean_p']:>8.3f}{s['happened']:>10.3f}")
        for s, sc in block["occurrence"].items():
            lines.append(f"  {s:<36}Brier {sc['brier']:.3f}  log loss {sc['log_loss']:.3f}")
    return "\n".join(lines)


def sweep(levels, seeds: int, events: int = 120, log=print) -> dict:
    out: dict = {"levels": list(levels), "runs": []}
    with tempfile.TemporaryDirectory() as tmp:
        for c in levels:
            for s in range(1, seeds + 1):
                path = Path(tmp) / f"c{c}-s{s}"
                simulate.generate(path, events=events, contamination=c, seed=s)
                out["runs"].append({"contamination": c, "seed": s, "result": run(load(path))})
                log(f"contamination {c:.1f} seed {s} done")
    return out


def _at(summary: dict, c: float) -> list[dict]:
    return [r["result"] for r in summary["runs"] if r["contamination"] == c]


def _row(summary: dict, label: str, pick, fmt: str = "{:>9.3f}") -> str:
    cells = "".join(
        fmt.format(float(np.mean([pick(r) for r in _at(summary, c)]))) for c in summary["levels"]
    )
    return f"{label:<34}{cells}"


def sweep_table(summary: dict, cp: str = "final") -> str:
    levels = summary["levels"]
    cols = "".join(f"{f'{c:.0%}':>9}" for c in levels)
    lines = []
    for metric in ("ece_adaptive", "brier", "log_loss", "bias"):
        head = f"{PROPOSED}, {metric} at {cp}"
        head = f"{head:<34}{cols}"
        lines += [head, "-" * len(head)]
        for cal in CALIBRATORS:
            lines.append(
                _row(
                    summary,
                    cal,
                    lambda r, cal=cal, m=metric: r["calibration"]["checkpoints"][cp]["methods"][
                        PROPOSED
                    ][cal][m],
                    "{:>+9.3f}" if metric == "bias" else "{:>9.3f}",
                )
            )
        lines.append("")
    head = f"{'platt, ece_adaptive at ' + cp:<34}{cols}"
    lines += [head, "-" * len(head)]
    for m in method_list():
        lines.append(
            _row(
                summary,
                m.name,
                lambda r, n=m.name: r["calibration"]["checkpoints"][cp]["methods"][n]["platt"][
                    "ece_adaptive"
                ],
            )
        )
    lines.append("")
    head = f"{'occurrence Brier at ' + cp:<34}{cols}"
    lines += [head, "-" * len(head)]
    for s in SIGNALS:
        lines.append(
            _row(
                summary,
                s,
                lambda r, s=s: r["labels"]["checkpoints"][cp]["occurrence"][s]["brier"],
            )
        )
    lines.append("")
    head = f"{'labels at ' + cp + ': n / mean p / happened':<34}" + "".join(
        f"{f'{c:.0%}':>20}" for c in levels
    )
    lines += [head, "-" * len(head)]
    for lab in assess.LABELS:
        cells = []
        for c in levels:
            stats = [r["labels"]["checkpoints"][cp]["by_label"][lab] for r in _at(summary, c)]
            n = sum(s["n"] for s in stats)
            if not n:
                cells.append(f"{'-':>20}")
                continue
            mp = sum(s["n"] * s["mean_p"] for s in stats if s["n"]) / n
            hp = sum(s["n"] * s["happened"] for s in stats if s["n"]) / n
            cells.append(f"{f'{n} / {mp:.2f} / {hp:.2f}':>20}")
        lines.append(f"{lab:<34}" + "".join(cells))
    return "\n".join(lines)


def pooled_reliability(summary: dict, c: float, cp: str, cal: str, bins: int = 10) -> list[dict]:
    """Reliability-diagram bins over all seeds' held-out predictions at one level."""
    p, y = [], []
    for r in _at(summary, c):
        block = r["calibration"]["checkpoints"][cp]
        p += block["predictions"][cal]
        y += block["truth"]
    return metrics.reliability(np.array(p), np.array(y), bins)


def figures(summary: dict, out_dir: str | Path) -> list[Path]:
    """Reliability diagrams (needs matplotlib: pip install -e ".[figures]")."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    styles = {"none": ("#b0b0b0", "s"), "platt": ("#1f5fa8", "o"), "isotonic": ("#d07a1a", "^")}
    for cp in ("T+6h", "final"):
        levels = summary["levels"]
        fig, axes = plt.subplots(
            2,
            len(levels),
            figsize=(3.4 * len(levels), 4.6),
            sharex=True,
            gridspec_kw={"height_ratios": [3, 1]},
            squeeze=False,
        )
        for col, c in enumerate(levels):
            ax, hist = axes[0, col], axes[1, col]
            ax.plot([0, 1], [0, 1], color="#888", lw=0.8, ls="--")
            for cal, (color, marker) in styles.items():
                bins = [b for b in pooled_reliability(summary, c, cp, cal) if b["n"] >= MIN_BIN]
                ax.plot(
                    [b["predicted"] for b in bins],
                    [b["observed"] for b in bins],
                    marker=marker,
                    color=color,
                    lw=1.4,
                    ms=4,
                    label=cal,
                )
            counts = [b["n"] for b in pooled_reliability(summary, c, cp, "platt")]
            hist.bar(np.arange(10) / 10 + 0.05, counts, width=0.09, color="#1f5fa8", alpha=0.6)
            hist.set_yscale("symlog")
            hist.set_xlabel("predicted probability")
            ax.set_title(f"contamination {c:.0%}", fontsize=10)
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
        axes[0, 0].set_ylabel("share that happened")
        axes[1, 0].set_ylabel("events (platt)")
        axes[0, -1].legend(loc="upper left", fontsize=8, frameon=False)
        fig.suptitle(
            f"{PROPOSED} at {cp} (simulated, pooled over seeds; bins with < {MIN_BIN} "
            "events hidden)",
            fontsize=10,
        )
        fig.tight_layout()
        path = out_dir / f"reliability-{cp.replace('+', '')}.png"
        fig.savefig(path, dpi=200, bbox_inches="tight")
        plt.close(fig)
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m carcux_fusion.calibrate")
    parser.add_argument("dataset", nargs="?")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--simulate", action="store_true", help="sweep simulated sets instead")
    parser.add_argument("--levels", type=float, nargs="+", default=[0.0, 0.3, 0.6])
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--figures", help="write reliability diagrams here (simulate only)")
    parser.add_argument("--json")
    args = parser.parse_args(argv)
    if args.simulate:
        result = sweep(args.levels, args.seeds)
        print()
        for cp in ("T+6h", "final"):
            print(sweep_table(result, cp))
            print()
        if args.figures:
            for path in figures(result, args.figures):
                print(f"wrote {path}")
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
