"""The final real-data test (results/rumoureval-test/PLAN.md): every method learns from
PHEME and is judged once on the RumourEval 2019 English Twitter test set.

    python -m carcux_fusion.rumoureval_test PHEME_DIR RUMOUREVAL_DIR --out DIR

- Training events: PHEME's true and false stories, with stance from the development
  stance model, cross-fitted by crisis (as in development).
- Test events: each RumourEval 2019 Twitter test thread (true or false; unverified ones
  are counted and left out). Stance, primary: the development stance model trained on
  all RumourEval training and development labels; secondary: the test set's own gold
  stance, as an upper bound.
- Methods: majority (B3), TruthFinder (B5), B7 and B7 with labels, the first proposed
  model (no reply links) and the revised one. Brier, ECE, AUC, accuracy, and a paired
  bootstrap of the revised model against each, at T+1h, T+6h and final.

Writes `result-predicted-stance.json`, `result-gold-stance.json` and `summary.txt` to
`--out`, with the commit the code was run from. Tweet text is never written.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from carcux_fusion import evaluate, pheme
from carcux_fusion import methods as M
from carcux_fusion.data import Dataset
from carcux_fusion.social import SocialSensing

TEST_GROUP = "rumoureval-2019-test"


def methods() -> list[M.Method]:
    return [
        M.Majority(),
        M.TruthFinder(),
        SocialSensing(dependence=True, silence=False),
        SocialSensing(dependence=True, silence=False, supervised=True),
        M.Reliability("detected", structure=False),  # the first proposed model
        M.Reliability("detected"),  # revised: reply links, cross-fitted calibration
    ]


def load_test_threads(re_dir: str | Path) -> list[pheme.Thread]:
    """The English Twitter test threads, with veracity from the gold key."""
    root = Path(re_dir)
    key = json.loads((root / "final-eval-key.json").read_text(encoding="utf-8"))
    veracity = key["subtaskbenglish"]
    base = next(root.rglob("twitter-en-test-data"))
    threads = []
    for d in sorted(p for p in base.glob("*/*") if p.is_dir() and not p.name.startswith(".")):
        if d.name not in veracity:
            continue
        t = pheme.Thread(d.name, TEST_GROUP, d.name, veracity[d.name])
        for f in sorted([*(d / "source-tweet").glob("*.json"), *(d / "replies").glob("*.json")]):
            if not f.name.startswith("."):
                tw = pheme._tweet(f)
                if tw:
                    t.tweets.append(tw)
        threads.append(t)
    return threads


def merge(a: Dataset, b: Dataset) -> Dataset:
    return Dataset(
        {**a.events, **b.events},
        {**a.observations, **b.observations},
        {**a.source_type, **b.source_type},
        {**a.dependences, **b.dependences},
        name="pheme+rumoureval-test",
        structure={**a.structure, **b.structure},
    )


def run(pheme_dir, re_dir) -> dict:
    train_threads = pheme.load_threads(pheme_dir)
    gold = pheme.load_stance(re_dir)
    train_stance, stance_scores = pheme.cross_fitted_stance(train_threads, gold)
    train, _, train_counts = pheme.build(train_threads, train_stance, only_labelled=False)

    model = pheme.StanceModel("cues")
    labelled = [(i, gold[tid]) for t in train_threads for tid, i in pheme.stance_items(t)
                if tid in gold]  # fmt: skip
    model.fit([i for i, _ in labelled], [y for _, y in labelled])
    test_threads = load_test_threads(re_dir)
    items = [(tid, i) for t in test_threads for tid, i in pheme.stance_items(t)]
    predicted = dict(zip([tid for tid, _ in items], model.predict([i for _, i in items]),
                         strict=True))  # fmt: skip
    key = json.loads((Path(re_dir) / "final-eval-key.json").read_text(encoding="utf-8"))
    test_gold = key["subtaskaenglish"]

    out = {"training": train_counts, "stance_model_development": stance_scores}
    for name, stance in (("predicted-stance", predicted), ("gold-stance", test_gold)):
        test, _, test_counts = pheme.build(test_threads, stance, only_labelled=False)
        data = merge(train, test)
        result = evaluate.run(
            data,
            parts=[sorted(train.events), sorted(test.events)],
            test_folds=[1],
            copy_threshold=pheme.COPY_THRESHOLD,
            method_list=methods(),
        )
        result["test"] = test_counts
        out[name] = result
    return out


def _commit() -> str:
    cmd = ["git", "rev-parse", "HEAD"]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, check=True)  # noqa: S603, S607
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return done.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m carcux_fusion.rumoureval_test")
    parser.add_argument("pheme")
    parser.add_argument("rumoureval")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    commit = _commit()
    result = run(args.pheme, args.rumoureval)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    lines = [f"Commit: {commit}", ""]
    for name in ("predicted-stance", "gold-stance"):
        r = result[name]
        r["commit"] = commit
        (out / f"result-{name}.json").write_text(json.dumps(r, indent=2), encoding="utf-8")
        lines += [f"== {name}: {json.dumps(r['test'])}", evaluate.table(r), ""]
    (out / "summary.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
