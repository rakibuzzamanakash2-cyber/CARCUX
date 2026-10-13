"""The streaming evaluator must agree with the all-pairs code it scales up."""

import json

import numpy as np
import pytest

from carcux_correlation import features as F
from carcux_correlation import models, simulate, stream
from carcux_correlation.benchmarks import news_clustering
from carcux_correlation.data import load
from carcux_correlation.metrics import _partition_scores, bcubed, pairwise


@pytest.fixture(scope="module")
def sim_stream(tmp_path_factory):
    out = tmp_path_factory.mktemp("sim")
    simulate.generate(out, events=12, seed=5)
    obs = load(out).observations
    vec = stream.make_vectorizer("char")
    vec.set_params(min_df=1)
    vec.fit([o.text.lower() for o in obs])
    return stream.build(obs, vec)


def test_streamed_features_match_pair_features(sim_stream):
    s = sim_stream
    cos = (s.vectors @ s.vectors.T).toarray()
    for i, f in stream.rows(s):
        for j in range(i):
            expected = F.pair_features(s.obs[i], s.obs[j], float(np.clip(cos[i, j], 0, 1)))
            assert f[j] == pytest.approx(expected, abs=1e-6), (i, j)


def test_streamed_rules_match_all_pairs_rules(sim_stream):
    s = sim_stream
    full = np.zeros((len(s), len(s), len(F.NAMES)))
    for i, f in stream.rows(s):
        full[i, :i] = f
        full[:i, i] = f
    idx = list(range(len(s)))
    expected = models.TextThenRules().scores(s.obs, full, idx)
    rule = stream.TextRules()
    for i, f in stream.rows(s):
        got = rule(f)
        assert (got == 0) == pytest.approx(expected[i, :i] == 0)


def test_multi_threshold_clustering_matches_single_runs(sim_stream):
    s = sim_stream
    full = np.eye(len(s))
    for i, f in stream.rows(s):
        full[i, :i] = full[:i, i] = f[:, F.NAMES.index("text_cos")]
    thresholds = [0.1, 0.3, 0.6]
    labels = stream.cluster(s, stream.Text(), thresholds)
    for t, th in enumerate(thresholds):
        assert labels[t].tolist() == models.cluster(full, th)


def _brute_force(pred, gold):
    n = len(pred)
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    tp = sum(pred[i] == pred[j] and gold[i] == gold[j] for i, j in pairs)
    pp = sum(pred[i] == pred[j] for i, j in pairs)
    gp = sum(gold[i] == gold[j] for i, j in pairs)
    p = tp / pp if pp else 1.0
    r = tp / gp if gp else 1.0
    bp = np.mean(
        [np.mean([gold[j] == gold[i] for j in range(n) if pred[j] == pred[i]]) for i in range(n)]
    )
    br = np.mean(
        [np.mean([pred[j] == pred[i] for j in range(n) if gold[j] == gold[i]]) for i in range(n)]
    )
    return p, r, bp, br


def test_fast_metrics_match_definitions():
    rng = np.random.default_rng(1)
    for _ in range(30):
        n = int(rng.integers(2, 40))
        pred = rng.integers(0, 6, n).tolist()
        gold = [str(g) for g in rng.integers(0, 5, n)]
        (p, r, _), (bp, br, _) = _partition_scores(pred, gold)
        assert (p, r, bp, br) == pytest.approx(_brute_force(pred, gold))
        # The public functions take the fast path for single-event gold.
        assert pairwise(pred, [{g} for g in gold])[:2] == pytest.approx((p, r))
        assert bcubed(pred, [{g} for g in gold])[:2] == pytest.approx((bp, br))


def _write_fake_news(path, n_clusters, per, seed, lang="eng"):
    rng = np.random.default_rng(seed)
    records = []
    for c in range(n_clusters):
        words = [f"topic{c}word{k}" for k in range(8)]
        for k in range(per):
            text = " ".join(rng.choice(words, 30).tolist() + [f"common{k}"] * 3)
            records.append(
                {
                    "id": f"{seed}-{c}-{k}",
                    "title": f"story {c}",
                    "text": text,
                    "event_id": str(c),
                    "duplicate": False,
                    "lang": lang,
                    "bag_id": "b",
                    "date": f"2014-0{1 + c % 9}-1{k % 10} 0{k % 10}:00:00",
                    "source": "made up",
                    "cluster": str(c),
                }
            )
    records.append({**records[0], "id": "other-lang", "lang": "spa"})
    path.write_text(json.dumps(records), encoding="utf-8")


def test_news_loader_keeps_one_language_in_date_order(tmp_path):
    _write_fake_news(tmp_path / "dataset.dev.json", 3, 4, seed=1)
    obs = news_clustering.load(tmp_path / "dataset.dev.json", "eng")
    assert len(obs) == 12
    assert all(o.language == "en" and not o.located for o in obs)
    assert [o.time for o in obs] == sorted(o.time for o in obs)
    assert obs[0].events == {obs[0].primary} and obs[0].primary.startswith("eng:")


def test_news_benchmark_end_to_end(tmp_path):
    _write_fake_news(tmp_path / "dataset.dev.json", 6, 6, seed=1)
    _write_fake_news(tmp_path / "dataset.test.json", 5, 5, seed=2)
    out = tmp_path / "r.json"
    assert news_clustering.main([str(tmp_path), "--lang", "eng", "--json", str(out)]) == 0
    (result,) = json.loads(out.read_text())
    assert set(result["methods"]) == {"text", "text+rules", "joint", "joint-time"}
    assert result["test_articles"] == 25
    for m in result["methods"].values():
        assert all(0 <= m[k] <= 1 for k in ("pair_precision", "pair_recall", "bcubed_f1"))


def test_news_benchmark_reports_missing_files(tmp_path, capsys):
    assert news_clustering.main([str(tmp_path), "--lang", "eng"]) == 1
    assert "eng" in capsys.readouterr().err
