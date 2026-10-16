"""How well the checks and the account score find simulated misuse.

    python -m carcux_integrity.evaluate                  # 60 workers, 18 misused, 3 seeds
    python -m carcux_integrity.evaluate --seeds 5 --json integrity.json
    python -m carcux_integrity.evaluate --first-seed 3 --seeds 5   # fresh worlds

Report level (the last day): for each flag, how many of the reports it marks are misuse
(precision) and how many misuse reports of each scenario it catches (recall). Account
level: whether the score ranks misused accounts above ordinary ones (AUC), and precision
and recall at a score of 0.5 or more.
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import timedelta

from carcux_integrity.account import score
from carcux_integrity.checks import Text, check
from carcux_integrity.simulate import SCENARIOS, simulate

REVIEW_FROM = 0.5


def run(seed: int, workers: int = 60, compromised: int = 18) -> dict:
    w = simulate(workers=workers, compromised=compromised, seed=seed)
    ordered = sorted(w.reports, key=lambda r: r.received_at)
    flags: dict[str, list] = {}
    texts = list(w.public)
    for i, r in enumerate(ordered):
        flags[r.id] = check(r, ordered[:i], texts)
        texts.append(Text(r.id, r.text, "report", r.account))
    last_day = [r for r in ordered if r.received_at >= w.now - timedelta(days=1)]
    by_code: dict[str, dict[str, int]] = defaultdict(lambda: {"misuse": 0, "ordinary": 0})
    caught: dict[str, dict[str, int]] = {s: {"reports": 0, "any_flag": 0} for s in SCENARIOS}
    for r in last_day:
        bad = r.id in w.injected
        for code in {f.code for f in flags[r.id]}:
            by_code[code]["misuse" if bad else "ordinary"] += 1
        if bad:
            s = w.report_scenario[r.id]
            caught[s]["reports"] += 1
            caught[s]["any_flag"] += bool(flags[r.id])
    ordinary_last = [r for r in last_day if r.id not in w.injected]
    accounts = sorted({r.account for r in w.reports})
    risks = {a: score(a, w.reports, flags, w.now) for a in accounts}
    return {
        "seed": seed,
        "flags": dict(by_code),
        "scenario_reports": caught,
        "ordinary_reports_last_day": len(ordinary_last),
        "ordinary_flagged_last_day": sum(1 for r in ordinary_last if flags[r.id]),
        "accounts": {a: {"score": risks[a].score, "scenario": w.scenario.get(a)} for a in accounts},
    }


def _auc(pos: list[float], neg: list[float]) -> float | None:
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def summarise(runs: list[dict]) -> dict:
    codes: dict[str, dict[str, int]] = defaultdict(lambda: {"misuse": 0, "ordinary": 0})
    scen = {s: {"reports": 0, "any_flag": 0} for s in SCENARIOS}
    acc_scen = {s: {"accounts": 0, "reviewed": 0} for s in SCENARIOS}
    pos, neg = [], []
    ordinary_n = ordinary_flagged = 0
    for r in runs:
        for c, v in r["flags"].items():
            codes[c]["misuse"] += v["misuse"]
            codes[c]["ordinary"] += v["ordinary"]
        for s, v in r["scenario_reports"].items():
            scen[s]["reports"] += v["reports"]
            scen[s]["any_flag"] += v["any_flag"]
        ordinary_n += r["ordinary_reports_last_day"]
        ordinary_flagged += r["ordinary_flagged_last_day"]
        for a in r["accounts"].values():
            if a["scenario"]:
                pos.append(a["score"])
                acc_scen[a["scenario"]]["accounts"] += 1
                acc_scen[a["scenario"]]["reviewed"] += a["score"] >= REVIEW_FROM
            else:
                neg.append(a["score"])
    tp = sum(p >= REVIEW_FROM for p in pos)
    fp = sum(n >= REVIEW_FROM for n in neg)
    return {
        "seeds": [r["seed"] for r in runs],
        "flag_precision": {
            c: v["misuse"] / (v["misuse"] + v["ordinary"]) for c, v in codes.items()
        },
        "flag_counts": dict(codes),
        "scenario_recall": {
            s: v["any_flag"] / v["reports"] if v["reports"] else None for s, v in scen.items()
        },
        "ordinary_flagged_share": ordinary_flagged / ordinary_n if ordinary_n else None,
        "account_auc": _auc(pos, neg),
        "account_precision": tp / (tp + fp) if tp + fp else None,
        "account_recall": tp / len(pos) if pos else None,
        "account_recall_by_scenario": {
            s: v["reviewed"] / v["accounts"] if v["accounts"] else None for s, v in acc_scen.items()
        },
        "accounts": {"misused": len(pos), "ordinary": len(neg)},
    }


def _f(x) -> str:
    return "-" if x is None else f"{x:.3f}"


def table(s: dict) -> str:
    lines = [
        f"Seeds {s['seeds']}: {s['accounts']['misused']} misused and "
        f"{s['accounts']['ordinary']} ordinary accounts",
        "",
        "Flags on the last day (precision: share of flagged reports that are misuse):",
    ]
    for c, p in sorted(s["flag_precision"].items()):
        n = s["flag_counts"][c]
        lines.append(
            f"  {c:<24} precision {p:.3f}  ({n['misuse']} misuse, {n['ordinary']} ordinary)"
        )
    lines.append(f"  ordinary reports flagged: {_f(s['ordinary_flagged_share'])}")
    lines += ["", "Misuse reports caught by any flag, per scenario:"]
    for sc, r in s["scenario_recall"].items():
        lines.append(f"  {sc:<16} {_f(r)}")
    lines += [
        "",
        f"Account score: AUC {_f(s['account_auc'])}; at ≥ {REVIEW_FROM}: precision "
        f"{_f(s['account_precision'])}, recall {_f(s['account_recall'])}",
    ]
    for sc, r in s["account_recall_by_scenario"].items():
        lines.append(f"  {sc:<16} accounts marked for review {_f(r)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m carcux_integrity.evaluate")
    ap.add_argument("--seeds", type=int, default=3, help="how many simulated worlds")
    ap.add_argument(
        "--first-seed",
        type=int,
        default=0,
        help="0-2 were used while choosing thresholds; 3+ are fresh",
    )
    ap.add_argument("--json")
    args = ap.parse_args(argv)
    s = summarise([run(seed) for seed in range(args.first_seed, args.first_seed + args.seeds)])
    print(table(s))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
