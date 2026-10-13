"""Multilingual news stream clustering benchmark (Miranda et al., EMNLP 2018).

News articles in English, German and Spanish, each labelled with a fine-grained story
cluster, with a publication time. It has no coordinates, so it tests meaning and time,
not place. The protocol follows the authors' scorer (github.com/priberam/news-clustering):
one language at a time, articles in date order, every article counted (duplicates
included), pairwise precision/recall/F1 against `cluster`. We train and tune on
`dataset.dev.json` and report on `dataset.test.json`.

The data is not in this repository (size, and its licence is not stated). Download the
two files (see ai/correlation/README.md), then:

    python -m carcux_correlation.benchmarks.news_clustering DIR [--lang eng deu spa]
        [--text word|char] [--seeds 3] [--json results.json]

Differences between methods are tested with a paired bootstrap over test stories
(`significance.py`); `--seeds N` repeats the trained methods with N training seeds.
"""

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from carcux_correlation import cluster_model, significance, stream
from carcux_correlation.data import Obs
from carcux_correlation.stream import Outcome

LANGS = {"eng": "en", "deu": "de", "spa": "es"}
# Best monolingual pairwise F1 reported by Miranda et al. (2018), for reference.
# Their system used lemmas, named entities and timestamps with learned ranking/merging.
REPORTED_F1 = {"eng": 0.941, "deu": 0.971, "spa": 0.942}


def load(path: str | Path, lang: str) -> list[Obs]:
    """Articles of one language from dataset.{dev,test}.json, as `Obs`, in date order."""
    with open(path, encoding="utf-8") as fh:
        records = json.load(fh)
    out = []
    for r in records:
        if r["lang"] != lang:
            continue
        when = datetime.strptime(r["date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        cluster = f"{lang}:{r['cluster']}"
        out.append(
            Obs(
                obs_id=str(r["id"]),
                text=f"{r.get('title') or ''}\n{r.get('text') or ''}",
                language=LANGS.get(lang, lang),
                time=when,
                published=when,
                lat=None,
                lon=None,
                precision_m=None,
                event_type=None,
                events={cluster},
                roots={cluster},
                primary=cluster,
            )
        )
    out.sort(key=lambda o: (o.time, o.obs_id))
    return out


# Each pair: (baseline, proposed). Positive differences favour the proposed method.
COMPARISONS = [
    ("ctext", "cjoint"),  # RQ1, like for like: does adding time help?
    ("text", "cjoint"),  # against B1
    ("text+rules", "cjoint"),  # against B2
    ("cjoint-recency", "cjoint"),  # do the recency terms help?
]


def method_list(with_pair_joint: bool = False) -> list:
    """B1 and B2, then the cluster-level models. The pair-level joint model failed on this
    benchmark (see the README) and is only run when asked for."""
    keep = {"text", "text+rules"} | ({"joint", "joint-time"} if with_pair_joint else set())
    pair = [m for m in stream.methods() if m.name in keep]
    # No article has a location, so a "without place" ablation would equal the full model.
    return pair + cluster_model.methods(with_space=False, with_recency_ablation=True)


def run_language(
    directory: Path,
    lang: str,
    *,
    text: str = "word",
    seed: int = 0,
    seeds: int = 1,
    resamples: int = 2000,
    with_pair_joint: bool = False,
    log=print,
) -> dict:
    started = time.time()
    train_obs = load(directory / "dataset.dev.json", lang)
    test_obs = load(directory / "dataset.test.json", lang)
    if not train_obs or not test_obs:
        raise ValueError(f"no {lang} articles in {directory}")
    log(f"{lang}: {len(train_obs)} training articles, {len(test_obs)} test articles")
    max_chars = None if text == "word" else 1500
    vectorizer = stream.make_vectorizer(text)
    vectorizer.fit([(o.text or "")[:max_chars].lower() for o in train_obs])
    train = stream.build(train_obs, vectorizer, max_chars)
    test = stream.build(test_obs, vectorizer, max_chars)

    runs: list[list[Outcome]] = []
    for k in range(seeds):
        if seeds > 1:
            log(f"  seed {seed + k}")
        methods = method_list(with_pair_joint)
        if k > 0:  # only trained methods change with the seed
            methods = [m for m in methods if getattr(m, "trainable", False) or hasattr(m, "prob")]
        runs.append(stream.run(train, test, methods, seed=seed + k, log=log))

    first = {o.method: o for o in runs[0]}
    comparisons = []
    for a, b in COMPARISONS:
        if a in first and b in first:
            c = significance.paired_bootstrap(
                first[a].pred,
                first[b].pred,
                test.gold,
                names=(a, b),
                resamples=resamples,
                seed=seed,
            )
            comparisons.append(c.as_dict())
            log("  " + c.line())
    by_seed: dict[str, list[dict]] = {}
    for outcomes in runs:
        for o in outcomes:
            by_seed.setdefault(o.method, []).append(_as_dict(o))
    return {
        "language": lang,
        "train_articles": len(train),
        "test_articles": len(test),
        "test_gold_clusters": len(set(test.gold)),
        "text_features": text,
        "reported_pair_f1": REPORTED_F1.get(lang),
        "seeds": [seed + k for k in range(seeds)],
        "seconds": round(time.time() - started, 1),
        "methods": {name: rows[0] for name, rows in by_seed.items()},
        "across_seeds": {
            name: {
                key: {
                    "mean": float(np.mean([r[key] for r in rows])),
                    "sd": float(np.std([r[key] for r in rows])),
                }
                for key in ("bcubed_f1", "pair_f1")
            }
            for name, rows in by_seed.items()
            if len(rows) > 1
        },
        "comparisons": comparisons,
    }


def _as_dict(o: Outcome) -> dict:
    return {
        "threshold": o.threshold,
        "train_bcubed_f1": o.train_bcubed_f1,
        **o.test.as_dict(),
        **({"weights": o.weights} if o.weights else {}),
    }


COLUMNS = ["pair_precision", "pair_recall", "pair_f1", "bcubed_f1", "ari", "clusters"]


def table(results: list[dict]) -> str:
    head = f"{'lang':<5}{'method':<15}" + "".join(f"{c:>15}" for c in COLUMNS)
    lines = [head, "-" * len(head)]
    for r in results:
        for name, m in r["methods"].items():
            cells = "".join(f"{m[c]:>15}" if c == "clusters" else f"{m[c]:>15.3f}" for c in COLUMNS)
            lines.append(f"{r['language']:<5}{name:<15}{cells}")
        lines.append(
            f"{r['language']:<5}{'(reported)':<15}{'':>15}{'':>15}"
            f"{r['reported_pair_f1']:>15.3f}{'':>15}{'':>15}{r['test_gold_clusters']:>15}"
        )
        for name, v in r.get("across_seeds", {}).items():
            b, p = v["bcubed_f1"], v["pair_f1"]
            lines.append(
                f"{'':<5}{name:<15}over {len(r['seeds'])} seeds: B-cubed F1 "
                f"{b['mean']:.3f} ±{b['sd']:.3f}, pairwise F1 {p['mean']:.3f} ±{p['sd']:.3f}"
            )
        if r.get("comparisons"):
            lines.append(f"{'':<5}B-cubed F1 differences (paired story bootstrap):")
            for c in r["comparisons"]:
                sig = "yes" if c["ci_low"] > 0 or c["ci_high"] < 0 else "no"
                lines.append(
                    f"{'':<7}{c['b']} - {c['a']:<15}{c['diff']:+.3f}  "
                    f"95% CI [{c['ci_low']:+.3f}, {c['ci_high']:+.3f}]  "
                    f"{significance.Comparison(**c).p_text()}  significant: {sig}"
                )
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m carcux_correlation.benchmarks.news_clustering")
    parser.add_argument("directory", help="folder with dataset.dev.json and dataset.test.json")
    parser.add_argument("--lang", nargs="+", default=list(LANGS), choices=list(LANGS))
    parser.add_argument("--text", choices=["word", "char"], default="word")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--seeds", type=int, default=1, help="runs with seed, seed+1, ...")
    parser.add_argument("--resamples", type=int, default=2000, help="bootstrap resamples")
    parser.add_argument("--with-pair-joint", action="store_true", help="also run the first design")
    parser.add_argument("--json", help="also write the full results here")
    args = parser.parse_args(argv)
    directory = Path(args.directory)
    results = []
    for lang in args.lang:
        try:
            results.append(
                run_language(
                    directory,
                    lang,
                    text=args.text,
                    seed=args.seed,
                    seeds=args.seeds,
                    resamples=args.resamples,
                    with_pair_joint=args.with_pair_joint,
                )
            )
        except (OSError, ValueError) as exc:
            print(f"{lang}: {exc}", file=sys.stderr)
            return 1
    print()
    print(table(results))
    print("(reported) = best pairwise F1 in Miranda et al. 2018; last column = gold clusters")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
