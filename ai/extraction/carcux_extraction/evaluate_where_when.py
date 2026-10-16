"""Score place and time extraction on labelled examples.

    python -m carcux_extraction.evaluate_where_when             # development examples
    python -m carcux_extraction.evaluate_where_when --held-out  # examples not tuned on

A place counts as found when its name and district match the label. A time counts as
found when its start (to the minute) and precision match the label.
"""

import argparse
import json
import sys
from datetime import datetime
from importlib.resources import files

from carcux_extraction.places import find_places
from carcux_extraction.times import times


def examples(name: str = "where_when_dev") -> list[dict]:
    text = files(__package__).joinpath("data", f"{name}.jsonl").read_text("utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else None
    return {"precision": p, "recall": r, "f1": f, "tp": tp, "fp": fp, "fn": fn}


def score(rows: list[dict]) -> dict:
    counts = {"places": [0, 0, 0], "times": [0, 0, 0]}
    misses = []
    for row in rows:
        published = datetime.fromisoformat(row["published"])
        got = {(p.name, p.district) for p in find_places(row["text"])}
        want = {(p["name"], p["district"]) for p in row["places"]}
        got_t = {(t.start.isoformat(), t.precision) for t in times(row["text"], published)}
        want_t = {(datetime.fromisoformat(t["start"]).isoformat(), t["precision"])
                  for t in row["times"]}  # fmt: skip
        for kind, g, w in (("places", got, want), ("times", got_t, want_t)):
            c = counts[kind]
            c[0] += len(g & w)
            c[1] += len(g - w)
            c[2] += len(w - g)
            if g != w:
                misses.append({"kind": kind, "text": row["text"], "extra": sorted(g - w),
                               "missing": sorted(w - g)})  # fmt: skip
    return {
        "examples": len(rows),
        "places": _prf(*counts["places"]),
        "times": _prf(*counts["times"]),
        "misses": misses,
    }


def _f(x) -> str:
    return "-" if x is None else f"{x:.3f}"


def table(result: dict) -> str:
    lines = [f"{result['examples']} examples"]
    for kind in ("places", "times"):
        r = result[kind]
        lines.append(
            f"  {kind:<7} precision {_f(r['precision'])}  recall {_f(r['recall'])}  "
            f"F1 {_f(r['f1'])}  (found {r['tp']}, extra {r['fp']}, missed {r['fn']})"
        )
    for m in result["misses"]:
        lines.append(
            f"  miss [{m['kind']}] {m['text']!r}: extra {m['extra']} missing {m['missing']}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m carcux_extraction.evaluate_where_when")
    ap.add_argument("--held-out", action="store_true", help="examples the rules were not tuned on")
    ap.add_argument("--json", help="write the scores here")
    args = ap.parse_args(argv)
    result = score(examples("where_when_held_out" if args.held_out else "where_when_dev"))
    print(table(result))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
