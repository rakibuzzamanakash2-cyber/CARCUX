"""PHEME and RumourEval as fusion data, on a tiny made-up copy of their layout."""

import json
from pathlib import Path

import pytest

from carcux_fusion import evaluate, pheme

CRISES = {
    "alpha": [("story one", "true"), ("story two", "false"), ("story three", "unverified")],
    "beta": [("story four", "true"), ("story five", "false")],
    "gamma": [("story six", "true"), ("story seven", "false")],
}
SUPPORT = ["this is confirmed by police", "confirmed, police say so", "yes confirmed true"]
DENY = ["this is fake, not true", "false rumour, fake", "not true, debunked fake"]


def _tweet(tid, user, minute, text, verified=False):
    return {"id": int(tid), "user": {"id": user, "verified": verified},
            "created_at": f"Wed Jan 07 11:{minute:02d}:00 +0000 2015", "text": text}  # fmt: skip


@pytest.fixture
def corpus(tmp_path: Path):
    root = tmp_path / "all-rnr-annotated-threads"
    stance: dict[str, str] = {}
    n = 1000
    for crisis, stories in CRISES.items():
        base = root / f"{crisis}-all-rnr-threads" / "rumours"
        for story, label in stories:
            for k in range(2):  # two threads per story
                n += 10
                d = base / str(n)
                (d / "source-tweets").mkdir(parents=True)
                (d / "reactions").mkdir()
                ann = {"category": story, "misinformation": int(label == "false"),
                       "true": str(int(label == "true"))}  # fmt: skip
                (d / "annotation.json").write_text(json.dumps(ann))
                src = _tweet(n, n % 7, 0, f"breaking: {story} reported", verified=k == 0)
                (d / "source-tweets" / f"{n}.json").write_text(json.dumps(src))
                stance[str(n)] = "support"
                replies = SUPPORT if label == "true" else DENY
                for r, text in enumerate(replies):
                    rid = n + r + 1
                    tw = _tweet(rid, 100 + r, r + 1, text)
                    (d / "reactions" / f"{rid}.json").write_text(json.dumps(tw))
                    stance[str(rid)] = "support" if label == "true" else "deny"
        (root / f"._{crisis}-all-rnr-threads").write_text("macOS metadata")
    key = tmp_path / "re" / "train-key.json"
    key.parent.mkdir()
    key.write_text(json.dumps({"subtaskaenglish": stance, "subtaskbenglish": {}}))
    return tmp_path, tmp_path / "re"


def test_veracity_rule():
    assert pheme.veracity({"misinformation": 0, "true": "1"}) == "true"
    assert pheme.veracity({"misinformation": 1, "true": "0"}) == "false"
    assert pheme.veracity({"misinformation": 0}) == "unverified"
    assert pheme.veracity({"misinformation": 1, "true": "1"}) is None
    assert pheme.veracity({"true": "1"}) is None


def test_threads_become_stories(corpus):
    root, re_dir = corpus
    threads = pheme.load_threads(root)
    assert len(threads) == 14 and {t.crisis for t in threads} == set(CRISES)
    data, crisis_of, counts = pheme.build(threads, pheme.load_stance(re_dir))
    assert counts["stories"] == 6 and counts["true"] == 3 and counts["false"] == 3
    assert counts["unverified threads"] == 2
    # Two threads of one story are one event; source tweets and replies all vote.
    one = data.events[pheme.story_id("alpha", "story one")]
    assert len(one.evidence) == 8 and one.occurred
    assert {v.vote for v in data.events[pheme.story_id("alpha", "story two")].evidence} == {1, -1}
    assert set(data.source_type.values()) == {"verified", "social"}
    assert [len(p) for p in pheme.by_crisis(crisis_of)] == [2, 2, 2]


def test_stance_is_learned_without_the_crisis_itself(corpus):
    root, re_dir = corpus
    threads = pheme.load_threads(root)
    stance, scores = pheme.cross_fitted_stance(threads, pheme.load_stance(re_dir))
    assert len(stance) == sum(len(t.tweets) for t in threads)
    assert scores["gold_tweets"] > 0 and 0 <= scores["macro_f1"] <= 1


def test_leave_one_crisis_out_runs(corpus):
    root, re_dir = corpus
    data, crisis_of, _ = pheme.build(pheme.load_threads(root), pheme.load_stance(re_dir))
    r = evaluate.run(data, parts=pheme.by_crisis(crisis_of), copy_threshold=pheme.COPY_THRESHOLD)
    assert r["folds"] == 3 and r["events"] == 6
    assert "majority" in r["checkpoints"]["final"]["methods"]


def test_replies_are_linked_to_their_conversation(corpus):
    root, re_dir = corpus
    data, _, _ = pheme.build(pheme.load_threads(root), pheme.load_stance(re_dir))
    assert data.structure and all(kind == "reply" for _, kind in data.structure.values())
    origins = {origin for origin, _ in data.structure.values()}
    assert origins <= set(data.observations)  # each conversation starts at a source tweet


def test_only_the_test_fold_is_judged(corpus):
    root, re_dir = corpus
    data, crisis_of, _ = pheme.build(pheme.load_threads(root), pheme.load_stance(re_dir))
    parts = pheme.by_crisis(crisis_of)
    r = evaluate.run(data, parts=parts, test_folds=[2], copy_threshold=pheme.COPY_THRESHOLD)
    assert r["judged"] == len(parts[2]) == 2


def test_supervised_calibration_is_cross_fitted():
    from carcux_fusion import methods as M

    assert M.Reliability("detected").supervised and not M.Majority().supervised
    assert M.Reliability("detected", structure=False).ignore_structure


@pytest.fixture
def test_set(tmp_path: Path):
    base = tmp_path / "re" / "test" / "twitter-en-test-data" / "topic"
    key = {"subtaskaenglish": {}, "subtaskbenglish": {}}
    for k, label in enumerate(["true", "false", "true", "false", "unverified"]):
        tid = str(9000 + 10 * k)
        d = base / tid
        (d / "source-tweet").mkdir(parents=True)
        (d / "replies").mkdir()
        (d / "source-tweet" / f"{tid}.json").write_text(json.dumps(_tweet(tid, 50 + k, 0, "news")))
        key["subtaskbenglish"][tid] = label
        key["subtaskaenglish"][tid] = "support"
        for r, text in enumerate(SUPPORT if label == "true" else DENY):
            rid = str(int(tid) + r + 1)
            (d / "replies" / f"{rid}.json").write_text(
                json.dumps(_tweet(rid, 200 + r, r + 1, text))
            )
            key["subtaskaenglish"][rid] = "support" if label == "true" else "deny"
    (tmp_path / "re" / "final-eval-key.json").write_text(json.dumps(key))
    return tmp_path / "re"


def test_final_test_runner_on_made_up_data(corpus, test_set):
    from carcux_fusion import rumoureval_test

    root, re_dir = corpus
    # The made-up training labels live in corpus's RumourEval folder; the test key here.
    (test_set / "train-key.json").write_text((re_dir / "train-key.json").read_text())
    threads = rumoureval_test.load_test_threads(test_set)
    assert len(threads) == 5 and threads[0].crisis == rumoureval_test.TEST_GROUP
    out = rumoureval_test.run(root, test_set)
    for name in ("predicted-stance", "gold-stance"):
        assert out[name]["judged"] == 4  # the unverified thread is left out
        assert out[name]["test"]["unverified threads"] == 1
        assert "reliability-dep" in out[name]["checkpoints"]["final"]["methods"]
