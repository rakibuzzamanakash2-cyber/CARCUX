import numpy as np
import pytest

from carcux_correlation.metrics import bcubed
from carcux_correlation.significance import bcubed_items, paired_bootstrap


def _gold(n_stories=30, size=6):
    return [f"s{k}" for k in range(n_stories) for _ in range(size)]


def test_per_item_scores_average_to_bcubed():
    rng = np.random.default_rng(0)
    gold = [str(g) for g in rng.integers(0, 8, 60)]
    pred = rng.integers(0, 10, 60).tolist()
    p, r = bcubed_items(pred, gold)
    want_p, want_r, _ = bcubed(pred, [{g} for g in gold])
    assert (p.mean(), r.mean()) == pytest.approx((want_p, want_r))


def test_identical_methods_show_no_difference():
    gold = _gold()
    pred = [k // 3 for k in range(len(gold))]
    c = paired_bootstrap(pred, pred, gold, resamples=300)
    assert c.diff == 0 and c.ci_low == 0 and c.ci_high == 0
    assert c.p_value == 1.0


def test_clearly_better_method_is_significant():
    gold = _gold()
    perfect = [int(g[1:]) for g in gold]
    singletons = list(range(len(gold)))
    c = paired_bootstrap(singletons, perfect, gold, names=("single", "perfect"), resamples=500)
    assert c.f1_b == pytest.approx(1.0)
    assert c.diff > 0 and c.ci_low > 0 and c.p_value < 0.01
    assert "significant" in c.line() and "not significant" not in c.line()


def test_bootstrap_is_seeded():
    gold = _gold()
    rng = np.random.default_rng(3)
    a = rng.integers(0, 40, len(gold)).tolist()
    b = rng.integers(0, 40, len(gold)).tolist()
    assert paired_bootstrap(a, b, gold, seed=1) == paired_bootstrap(a, b, gold, seed=1)
