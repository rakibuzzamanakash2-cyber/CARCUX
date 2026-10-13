"""Is one method's B-cubed F1 really higher than another's? A paired story bootstrap.

B-cubed precision and recall are averages of per-item scores, each computed on the
full clustering. Items about the same story are not independent, so we resample whole
gold stories (blocks) with replacement and recompute both methods' F1 on the same
resample. The spread of the difference gives a 95 % confidence interval, and the share
of resamples where the difference is not above zero gives a one-sided p-value (doubled
for two-sided, capped at 1).

Limits worth stating in the paper: per-item scores are computed once on the full
clustering (the clustering is not re-run per resample), and this measures uncertainty
from which stories happen to be in the test set, not from training randomness (use
several seeds for that).
"""

from dataclasses import dataclass

import numpy as np


def bcubed_items(pred, gold) -> tuple[np.ndarray, np.ndarray]:
    """Per-item B-cubed precision and recall when gold is a partition (one label each)."""
    _, p_idx = np.unique(np.asarray(pred), return_inverse=True)
    _, g_idx = np.unique(np.asarray(gold), return_inverse=True)
    _, cell = np.unique(p_idx * (g_idx.max() + 1) + g_idx, return_inverse=True)
    n_cell = np.bincount(cell)[cell].astype(float)
    return n_cell / np.bincount(p_idx)[p_idx], n_cell / np.bincount(g_idx)[g_idx]


def _f1(p, r):
    return np.where(p + r > 0, 2 * p * r / np.maximum(p + r, 1e-12), 0.0)


@dataclass(frozen=True)
class Comparison:
    a: str
    b: str
    f1_a: float
    f1_b: float
    diff: float
    ci_low: float
    ci_high: float
    p_value: float
    resamples: int

    def as_dict(self) -> dict:
        return self.__dict__.copy()

    def p_text(self) -> str:
        floor = 1 / self.resamples
        return f"p<{max(floor, 0.001):.3f}" if self.p_value < floor else f"p={self.p_value:.3f}"

    def line(self) -> str:
        sig = "significant" if self.ci_low > 0 or self.ci_high < 0 else "not significant"
        return (
            f"{self.a} vs {self.b}: {self.diff:+.3f} "
            f"[95% CI {self.ci_low:+.3f}, {self.ci_high:+.3f}], {self.p_text()} ({sig})"
        )


def paired_bootstrap(
    pred_a, pred_b, gold, *, names=("a", "b"), resamples: int = 2000, seed: int = 0
) -> Comparison:
    gold = np.asarray(gold)
    pa, ra = bcubed_items(pred_a, gold)
    pb, rb = bcubed_items(pred_b, gold)
    stories, story_of = np.unique(gold, return_inverse=True)
    n_st = len(stories)
    # Per-story sums, so each resample is a weighted sum over stories.
    sums = np.stack([np.bincount(story_of, weights=v, minlength=n_st) for v in (pa, ra, pb, rb)])
    counts = np.bincount(story_of, minlength=n_st).astype(float)

    def f1s(weights):
        n = weights @ counts
        p_a, r_a, p_b, r_b = (weights @ sums[k] / n for k in range(4))
        return _f1(p_a, r_a), _f1(p_b, r_b)

    ones = np.ones(n_st)
    f1_a, f1_b = (float(v) for v in f1s(ones))
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, n_st, size=(resamples, n_st))
    weights = np.zeros((resamples, n_st))
    np.add.at(weights, (np.repeat(np.arange(resamples), n_st), draws.ravel()), 1.0)
    boot_a, boot_b = f1s(weights)  # shapes (resamples,)
    diff = boot_b - boot_a  # b minus a, so a positive diff means b is better
    low, high = np.quantile(diff, [0.025, 0.975])
    p = min(1.0, 2 * min(np.mean(diff <= 0), np.mean(diff >= 0)))
    return Comparison(
        a=names[0],
        b=names[1],
        f1_a=f1_a,
        f1_b=f1_b,
        diff=f1_b - f1_a,
        ci_low=float(low),
        ci_high=float(high),
        p_value=float(p),
        resamples=resamples,
    )
