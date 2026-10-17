"""Real data: PHEME rumour stories as fusion events, with RumourEval stances.

    python -m carcux_fusion.pheme PHEME_DIR [--rumoureval RE_DIR] [--stance gold|model]
        [--json out.json]

**PHEME** (Kochkina, Liakata and Zubiaga 2018; `all-rnr-annotated-threads`): 2,402
Twitter rumour threads from 9 breaking-news crises (Charlie Hebdo, Sydney siege, Ottawa
shooting, Ferguson, Germanwings crash, and others). Journalists grouped threads into
**stories** (`annotation.json` `category`, for example "(At least) 10 people are dead at
Charlie Hebdo offices") and labelled each story true, false or unverified. Here:

- a story is a fusion **event**; `occurred` is true for a true story, false for a false
  one; unverified stories are left out of the true-or-false test, and counted;
- every tweet in the story's threads (source tweets and replies) is an **observation**;
- its author is the **source**; Twitter's `verified` flag is the source type
  (`verified` or `social`), the only account type the data gives;
- **stance** becomes the vote: support +1, deny -1, query and comment no vote.

**Stance** comes from either:

- `gold`: RumourEval 2019 (Gorrell et al. 2019) labels every tweet of 325 of these
  threads (subtask A, training and development keys). Only stories with at least one
  labelled thread are used, and only their labelled tweets;
- `model`: a stance classifier trained on those labels, applied to every tweet of every
  story. It is retrained for each held-out crisis without that crisis's tweets.

**Evaluation**: leave one crisis out (each crisis's stories are tested by methods that
learned only from the other crises), at T+1h, T+6h, T+24h and final after a story's
first tweet. Copies are detected with a fixed, pre-declared text threshold (PHEME has no
copy labels to tune one on).

Tweet text stays in memory: nothing here writes tweets to disk (CARCUX exports social
posts as links and labels only).
"""

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from carcux_fusion.data import Dataset, Event, Evidence, Observation

VOTES = {"support": 1, "deny": -1}
COPY_THRESHOLD = 0.8  # near-verbatim; fixed before any run on PHEME


@dataclass
class Tweet:
    tweet_id: str
    user_id: str
    verified: bool
    created: datetime
    text: str
    parent: str | None = None  # the tweet it replies to


@dataclass
class Thread:
    thread_id: str
    crisis: str
    story: str
    veracity: str  # true, false, unverified
    tweets: list[Tweet] = field(default_factory=list)


def veracity(annotation: dict) -> str | None:
    """PHEME's `misinformation` and `true` flags as a label (the authors' own rule)."""
    if "misinformation" not in annotation:
        return None
    false = int(annotation["misinformation"]) == 1
    true = int(annotation.get("true", 0)) == 1
    if false and true:
        return None
    return "false" if false else "true" if true else "unverified"


def _tweet(path: Path) -> Tweet | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        user = raw["user"]
        created = datetime.strptime(raw["created_at"], "%a %b %d %H:%M:%S %z %Y")
        parent = raw.get("in_reply_to_status_id_str") or raw.get("in_reply_to_status_id")
        return Tweet(str(raw["id"]), str(user["id"]), bool(user.get("verified")), created,
                     raw.get("text") or "", str(parent) if parent else None)  # fmt: skip
    except (OSError, ValueError, KeyError):
        return None


def load_threads(pheme_dir: str | Path) -> list[Thread]:
    root = Path(pheme_dir)
    if (root / "all-rnr-annotated-threads").is_dir():
        root = root / "all-rnr-annotated-threads"
    threads = []
    for crisis_dir in sorted(root.glob("*-all-rnr-threads")):
        if crisis_dir.name.startswith(".") or not (crisis_dir / "rumours").is_dir():
            continue  # macOS metadata ("._name") shipped in the archive
        crisis = crisis_dir.name.removesuffix("-all-rnr-threads")
        for d in sorted((crisis_dir / "rumours").iterdir()):
            if d.name.startswith(".") or not d.is_dir():
                continue
            try:
                ann = json.loads((d / "annotation.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            label = veracity(ann)
            if label is None or not ann.get("category"):
                continue
            t = Thread(d.name, crisis, ann["category"], label)
            for f in sorted(
                [*(d / "source-tweets").glob("*.json"), *(d / "reactions").glob("*.json")]
            ):
                if not f.name.startswith("."):
                    tw = _tweet(f)
                    if tw:
                        t.tweets.append(tw)
            threads.append(t)
    return threads


def load_stance(re_dir: str | Path) -> dict[str, str]:
    """RumourEval 2019 subtask A labels (training and development keys)."""
    root = Path(re_dir)
    out: dict[str, str] = {}
    for key in root.rglob("*-key.json"):
        if key.name in ("train-key.json", "dev-key.json"):
            out.update(json.loads(key.read_text(encoding="utf-8"))["subtaskaenglish"])
    return out


_NEGATION = re.compile(
    r"\b(not|no|fake|false|hoax|wrong|lie|lies|lying|debunk\w*|untrue|isn'?t|wasn'?t|aren'?t|"
    r"don'?t|doesn'?t|never|rumou?r|bs|bullshit|nonsense|misinform\w*|deny|denied|"
    r"unconfirmed|unverified|stop)\b"
)
_QUESTION = re.compile(r"\?|\b(really|is it|source|proof|confirm\w*|sure)\b")
STANCES = ["support", "deny", "query", "comment"]


@dataclass
class StanceItem:
    text: str
    source_text: str  # the thread's source tweet
    is_source: bool


class StanceModel:
    """Support, deny, query or comment, from a tweet and its thread's source tweet.

    `features="basic"`: word and character TF-IDF with a source/reply marker (the first
    real-data run). `features="cues"` (chosen on PHEME, leave one crisis out): also the
    source tweet's words, and cue counts (negations and "fake"/"hoax" words, questions,
    links, replies that start with a mention, length), with a more regularised logistic
    regression. Cross-crisis macro-F1 on PHEME's RumourEval labels: 0.477 basic, 0.509
    cues (denials 0.14 -> 0.18)."""

    def __init__(self, features: str = "cues"):
        self.features = features

    def _matrix(self, items: list[StanceItem], fit: bool):
        import numpy as np
        import scipy.sparse as sp

        marked = [("__source__ " if i.is_source else "__reply__ ") + i.text.lower() for i in items]
        parts = [self.words.fit_transform(marked) if fit else self.words.transform(marked)]
        if self.features == "cues":
            src = [i.source_text.lower() for i in items]
            parts.append(0.5 * (self.src.fit_transform(src) if fit else self.src.transform(src)))
            cues = [[len(_NEGATION.findall(i.text.lower())), len(_QUESTION.findall(i.text.lower())),
                     "?" in i.text, "http" in i.text, i.is_source, i.text.startswith("@"),
                     len(i.text) / 140] for i in items]  # fmt: skip
            parts.append(sp.csr_matrix(np.array(cues, dtype=float)))
        return sp.hstack(parts).tocsr()

    def fit(self, items: list[StanceItem], labels: list[str]) -> "StanceModel":
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import FeatureUnion

        self.words = FeatureUnion([
            ("words", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
            ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=2,
                                      sublinear_tf=True)),
        ])  # fmt: skip
        self.src = TfidfVectorizer(min_df=2, sublinear_tf=True)
        c = 0.5 if self.features == "cues" else 2.0
        self.model = LogisticRegression(max_iter=3000, class_weight="balanced", C=c)
        self.model.fit(self._matrix(items, fit=True), labels)
        return self

    def predict(self, items: list[StanceItem]) -> list[str]:
        return [str(x) for x in self.model.predict(self._matrix(items, fit=False))]


def stance_items(t: "Thread") -> list[tuple[str, StanceItem]]:
    source = next((tw for tw in t.tweets if tw.tweet_id == t.thread_id), None)
    src_text = source.text if source else ""
    return [(tw.tweet_id, StanceItem(tw.text, src_text, tw.tweet_id == t.thread_id))
            for tw in t.tweets]  # fmt: skip


def cross_fitted_stance(
    threads: list[Thread], gold: dict[str, str], features: str = "cues"
) -> tuple[dict, dict]:
    """Stance for every tweet from a model that never saw its crisis's labels: for each
    crisis, trained on the gold-labelled tweets of the other crises. Veracity labels are
    never used. Returns the stances and the model's cross-crisis scores on the gold
    tweets (macro-F1, as in RumourEval)."""
    from sklearn.metrics import f1_score

    rows = [(t.crisis, tid, item, gold.get(tid)) for t in threads for tid, item in stance_items(t)]
    out: dict[str, str] = {}
    true_all, pred_all = [], []
    for crisis in sorted({r[0] for r in rows}):
        train = [r for r in rows if r[0] != crisis and r[3]]
        test = [r for r in rows if r[0] == crisis]
        model = StanceModel(features).fit([r[2] for r in train], [r[3] for r in train])
        for r, label in zip(test, model.predict([r[2] for r in test]), strict=True):
            out[r[1]] = label
            if r[3]:
                true_all.append(r[3])
                pred_all.append(label)
    per_class = f1_score(true_all, pred_all, labels=STANCES, average=None, zero_division=0)
    scores = {
        "features": features,
        "gold_tweets": len(true_all),
        "macro_f1": float(
            f1_score(true_all, pred_all, labels=STANCES, average="macro", zero_division=0)
        ),  # fmt: skip
        "per_class_f1": {k: float(v) for k, v in zip(STANCES, per_class, strict=True)},
    }
    return out, scores


def story_id(crisis: str, story: str) -> str:
    return f"{crisis}:{hashlib.sha256(story.encode()).hexdigest()[:10]}"


def build(
    threads: list[Thread],
    stance: dict[str, str],
    *,
    only_labelled: bool = True,
) -> tuple[Dataset, dict[str, str], dict]:
    """A fusion dataset of true and false stories, the crisis of each, and counts.

    `stance` maps tweet ids to support/deny/query/comment. With `only_labelled`, threads
    without any stance label are dropped (the gold setting)."""
    events: dict[str, Event] = {}
    observations: dict[str, Observation] = {}
    source_type: dict[str, str] = {}
    crisis_of: dict[str, str] = {}
    structure: dict[str, tuple[str, str]] = {}
    skipped = Counter()
    for t in threads:
        if only_labelled and not any(tw.tweet_id in stance for tw in t.tweets):
            continue
        if t.veracity == "unverified":
            skipped["unverified threads"] += 1
            continue
        eid = story_id(t.crisis, t.story)
        ev = events.setdefault(eid, Event(eid, t.veracity == "true"))
        crisis_of[eid] = t.crisis
        for tw in t.tweets:
            vote = VOTES.get(stance.get(tw.tweet_id, ""))
            if not vote or tw.tweet_id in observations:
                continue
            observations[tw.tweet_id] = Observation(tw.tweet_id, tw.user_id, tw.created, tw.text)
            source_type[tw.user_id] = "verified" if tw.verified else "social"
            ev.evidence.append(Evidence(tw.tweet_id, vote))
            if tw.tweet_id != t.thread_id:
                # A reply belongs to the conversation its thread's source tweet started.
                structure[tw.tweet_id] = (t.thread_id, "reply")
    for eid in [e for e, ev in events.items() if not ev.evidence]:
        del events[eid]
        del crisis_of[eid]
        skipped["stories without votes"] += 1
    for ev in events.values():
        ev.evidence.sort(key=lambda x: (observations[x.obs_id].published, x.obs_id))
    data = Dataset(events, observations, source_type, {}, name="pheme", structure=structure)
    counts = {
        "stories": len(events),
        "true": sum(e.occurred for e in events.values()),
        "false": sum(not e.occurred for e in events.values()),
        "observations": len(observations),
        "sources": len(source_type),
        "sources_in_2plus_stories": sum(
            n >= 2
            for n in Counter(
                s
                for e in events.values()
                for s in {observations[x.obs_id].source_id for x in e.evidence}
            ).values()
        ),
        "crises": dict(Counter(crisis_of.values())),
        **{k: v for k, v in skipped.items()},
    }
    return data, crisis_of, counts


def by_crisis(crisis_of: dict[str, str]) -> list[list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for eid, c in sorted(crisis_of.items()):
        groups[c].append(eid)
    return [groups[c] for c in sorted(groups)]


def main(argv: list[str] | None = None) -> int:
    from carcux_fusion import evaluate

    parser = argparse.ArgumentParser(prog="python -m carcux_fusion.pheme")
    parser.add_argument("pheme")
    parser.add_argument("--rumoureval", required=True)
    parser.add_argument("--stance", choices=["gold", "model"], default="gold")
    parser.add_argument("--json")
    args = parser.parse_args(argv)
    threads = load_threads(args.pheme)
    gold = load_stance(args.rumoureval)
    if args.stance == "gold":
        data, crisis_of, counts = build(threads, gold)
    else:
        stance, stance_scores = cross_fitted_stance(threads, gold)
        data, crisis_of, counts = build(threads, stance, only_labelled=False)
        counts["stance_model"] = stance_scores
    counts["stance"] = args.stance
    print(json.dumps(counts, indent=1))
    result = evaluate.run(data, parts=by_crisis(crisis_of), copy_threshold=COPY_THRESHOLD)
    result["pheme"] = counts
    print(evaluate.table(result))
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
