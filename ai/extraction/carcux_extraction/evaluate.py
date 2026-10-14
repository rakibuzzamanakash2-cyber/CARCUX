"""How well extraction finds the details people label.

    python -m carcux_extraction.evaluate                  # the development examples
    python -m carcux_extraction.evaluate --held-out       # examples never tuned on
    python -m carcux_extraction.evaluate DATASET_DIR      # a CARCUX-BD export
    python -m carcux_extraction.evaluate DATASET_DIR --misses 20 --json out.json

Per attribute: precision (of the details extracted, how many match the label), recall
(of the labelled details, how many were extracted and match) and F1; macro averages;
and language accuracy. Values agree as in the annotation guideline (§5.2): counts
within ±20 %, everything else exactly. `occurrence` is scored only where it is false
(a denial), because every item about an event claims it by default.

The development examples (`carcux_extraction/data/dev.jsonl`) were written alongside
the rules, by hand, not taken from real reports: they show what the rules cover, not
how well they generalise. The held-out examples (`held_out.jsonl`) were written by
the same author after the rules, run once, and never used to change them: a fairer
but still optimistic check. The real test is a CARCUX-BD export with analysts' claims.
"""

import argparse
import json
import sys
from collections import defaultdict
from importlib import resources
from pathlib import Path

from carcux_extraction.claims import extract
from carcux_extraction.language import detect_language

ATTRIBUTES = ["occurrence", "casualty_count", "affected_count", "magnitude", "cause", "status"]
COUNT_TOLERANCE = 0.20


def agrees(attribute: str, a, b) -> bool:
    if attribute in ("casualty_count", "affected_count"):
        try:
            a, b = float(a), float(b)
        except (TypeError, ValueError):
            return False
        return abs(a - b) <= COUNT_TOLERANCE * max(abs(a), abs(b)) if max(a, b) else a == b
    if isinstance(a, str) and isinstance(b, str):
        return a.strip().lower() == b.strip().lower()
    return a == b


def _gold(claims: list[dict]) -> dict:
    out = {}
    for c in claims:
        a = c.get("attribute")
        if a not in ATTRIBUTES:
            continue
        if a == "occurrence" and c.get("value") is not False:
            continue
        out.setdefault(a, c.get("value"))
    return out


def dev_examples(name: str = "dev") -> list[dict]:
    path = resources.files("carcux_extraction") / "data" / f"{name}.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def dataset_examples(directory: str | Path) -> list[dict]:
    """Observations with text from a CARCUX-BD export."""
    path = Path(directory) / "observations.jsonl"
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [
        {"text": o["text"], "language": o.get("language"), "claims": o.get("claims", []),
         "id": o.get("obs_id")}
        for o in rows
        if o.get("text")
    ]  # fmt: skip


def score(examples: list[dict]) -> dict:
    counts = {a: {"tp": 0, "fp": 0, "fn": 0} for a in ATTRIBUTES}
    misses: list[dict] = []
    language_right = language_total = 0
    by_language: dict[str, dict] = defaultdict(lambda: {"right": 0, "total": 0})
    for ex in examples:
        gold = _gold(ex["claims"])
        got = {c.attribute: c.value for c in extract(ex["text"])}
        for a in ATTRIBUTES:
            g, p = a in gold, a in got
            if g and p and agrees(a, got[a], gold[a]):
                counts[a]["tp"] += 1
                continue
            if p:
                counts[a]["fp"] += 1
            if g:
                counts[a]["fn"] += 1
            if g or p:
                misses.append(
                    {"text": ex["text"], "attribute": a, "labelled": gold.get(a),
                     "extracted": got.get(a)}
                )  # fmt: skip
        if ex.get("language"):
            ok = detect_language(ex["text"]) == ex["language"]
            language_right += ok
            language_total += 1
            by_language[ex["language"]]["right"] += ok
            by_language[ex["language"]]["total"] += 1

    per = {}
    for a, c in counts.items():
        p = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else None
        r = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else None
        f = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
        per[a] = {**c, "precision": p, "recall": r, "f1": f, "labelled": c["tp"] + c["fn"]}
    scored = [v for v in per.values() if v["labelled"]]
    return {
        "examples": len(examples),
        "attributes": per,
        "macro_precision": _mean([v["precision"] for v in scored]),
        "macro_recall": _mean([v["recall"] for v in scored]),
        "macro_f1": _mean([v["f1"] for v in scored]),
        "language_accuracy": language_right / language_total if language_total else None,
        "language_by_label": {k: v["right"] / v["total"] for k, v in by_language.items()},
        "misses": misses,
    }


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _f(x) -> str:
    return "-" if x is None else f"{x:.3f}"


def table(result: dict, misses: int = 0) -> str:
    head = f"{'':<16}{'labelled':>9}{'precision':>11}{'recall':>9}{'F1':>8}"
    lines = [f"{result['examples']} examples", "", head, "-" * len(head)]
    for a, v in result["attributes"].items():
        lines.append(
            f"{a:<16}{v['labelled']:>9}{_f(v['precision']):>11}{_f(v['recall']):>9}{_f(v['f1']):>8}"
        )
    lines.append(
        f"{'macro':<16}{'':>9}{_f(result['macro_precision']):>11}"
        f"{_f(result['macro_recall']):>9}{_f(result['macro_f1']):>8}"
    )
    lines.append("")
    lines.append(
        f"language: {_f(result['language_accuracy'])} right ("
        + ", ".join(f"{k} {_f(v)}" for k, v in sorted(result["language_by_label"].items()))
        + ")"
    )
    if misses:
        lines += ["", "misses:"]
        for m in result["misses"][:misses]:
            lines.append(
                f"  {m['attribute']}: labelled {m['labelled']!r}, extracted {m['extracted']!r}"
                f"  |  {m['text'][:110]}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m carcux_extraction.evaluate")
    parser.add_argument("dataset", nargs="?", help="a CARCUX-BD export (default: dev examples)")
    parser.add_argument(
        "--held-out", action="store_true", help="the held-out examples (never tuned on)"
    )
    parser.add_argument("--misses", type=int, default=0, help="show this many mistakes")
    parser.add_argument("--json")
    args = parser.parse_args(argv)
    try:
        if args.dataset:
            examples = dataset_examples(args.dataset)
        else:
            examples = dev_examples("held_out" if args.held_out else "dev")
    except FileNotFoundError as exc:
        print(f"no observations found: {exc}", file=sys.stderr)
        return 1
    result = score(examples)
    print(table(result, args.misses))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
