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
        [--text word|char] [--json results.json]
"""

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from carcux_correlation import stream
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


def run_language(
    directory: Path, lang: str, *, text: str = "word", seed: int = 0, log=print
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
    # No article has a location, so "joint without place" is the same model as "joint".
    methods = [m for m in stream.methods() if m.name != "joint-space"]
    outcomes = stream.run(train, test, methods, seed=seed, log=log)
    return {
        "language": lang,
        "train_articles": len(train),
        "test_articles": len(test),
        "test_gold_clusters": len(set(test.gold)),
        "text_features": text,
        "reported_pair_f1": REPORTED_F1.get(lang),
        "seconds": round(time.time() - started, 1),
        "methods": {o.method: _as_dict(o) for o in outcomes},
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
    head = f"{'lang':<5}{'method':<13}" + "".join(f"{c:>15}" for c in COLUMNS)
    lines = [head, "-" * len(head)]
    for r in results:
        for name, m in r["methods"].items():
            cells = "".join(f"{m[c]:>15}" if c == "clusters" else f"{m[c]:>15.3f}" for c in COLUMNS)
            lines.append(f"{r['language']:<5}{name:<13}{cells}")
        lines.append(
            f"{r['language']:<5}{'(reported)':<13}{'':>15}{'':>15}"
            f"{r['reported_pair_f1']:>15.3f}{'':>15}{'':>15}{r['test_gold_clusters']:>15}"
        )
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m carcux_correlation.benchmarks.news_clustering")
    parser.add_argument("directory", help="folder with dataset.dev.json and dataset.test.json")
    parser.add_argument("--lang", nargs="+", default=list(LANGS), choices=list(LANGS))
    parser.add_argument("--text", choices=["word", "char"], default="word")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--json", help="also write the full results here")
    args = parser.parse_args(argv)
    directory = Path(args.directory)
    results = []
    for lang in args.lang:
        try:
            results.append(run_language(directory, lang, text=args.text, seed=args.seed))
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
