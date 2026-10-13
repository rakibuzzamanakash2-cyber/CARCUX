"""How well a grouping of observations matches the gold events.

Predictions are a partition (each observation in one cluster). Gold may overlap (one
report can describe both a waterlogging and the road blockage it caused), so:

- Pairwise precision / recall / F1: a pair is a gold positive if the two observations
  share any gold event; a predicted positive if they share a cluster.
- Extended B-cubed (Amigó, Gonzalo, Artiles and Verdejo, 2009), which allows items to
  belong to several gold categories.
- Adjusted Rand index against a partition of the gold (one primary event per item).

When every item has exactly one gold event, all three are computed from the contingency
table instead (same values, fast at benchmark scale).
"""

from dataclasses import dataclass
from itertools import combinations

import numpy as np
from sklearn.metrics import adjusted_rand_score


@dataclass(frozen=True)
class Scores:
    pair_precision: float
    pair_recall: float
    pair_f1: float
    bcubed_precision: float
    bcubed_recall: float
    bcubed_f1: float
    ari: float
    clusters: int
    gold_groups: int

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _f1(p: float, r: float) -> float:
    return 0.0 if p + r == 0 else 2 * p * r / (p + r)


def _partition_scores(pred, gold_labels) -> tuple[tuple, tuple]:
    """Pairwise and B-cubed from the contingency table: exact when gold is a partition,
    and fast enough for tens of thousands of items."""
    _, p_idx = np.unique(np.asarray(pred), return_inverse=True)
    _, g_idx = np.unique(np.asarray(gold_labels), return_inverse=True)
    _, cell = np.unique(p_idx * (g_idx.max() + 1) + g_idx, return_inverse=True)
    n_cell = np.bincount(cell).astype(float)  # items per (cluster, gold) cell
    cell_p = np.zeros(len(n_cell), dtype=int)
    cell_g = np.zeros(len(n_cell), dtype=int)
    cell_p[cell], cell_g[cell] = p_idx, g_idx
    size_p = np.bincount(p_idx).astype(float)
    size_g = np.bincount(g_idx).astype(float)

    def pairs(x):
        return float((x * (x - 1) / 2).sum())

    tp, pred_pairs, gold_pairs = pairs(n_cell), pairs(size_p), pairs(size_g)
    p = tp / pred_pairs if pred_pairs else 1.0
    r = tp / gold_pairs if gold_pairs else 1.0
    n = len(p_idx)
    bp = float((n_cell**2 / size_p[cell_p]).sum() / n)
    br = float((n_cell**2 / size_g[cell_g]).sum() / n)
    return (p, r, _f1(p, r)), (bp, br, _f1(bp, br))


def pairwise(pred: list[int], gold: list[set[str]]) -> tuple[float, float, float]:
    if pred and all(len(g) == 1 for g in gold):
        return _partition_scores(pred, [next(iter(g)) for g in gold])[0]
    tp = fp = fn = 0
    for i, j in combinations(range(len(pred)), 2):
        same_pred = pred[i] == pred[j]
        same_gold = bool(gold[i] & gold[j])
        tp += same_pred and same_gold
        fp += same_pred and not same_gold
        fn += same_gold and not same_pred
    # No positive pairs at all: nothing to get wrong on that side.
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    return p, r, _f1(p, r)


def bcubed(pred: list[int], gold: list[set[str]]) -> tuple[float, float, float]:
    """Extended B-cubed with a single predicted cluster per item."""
    n = len(pred)
    if n == 0:
        return 1.0, 1.0, 1.0
    if all(len(g) == 1 for g in gold):
        return _partition_scores(pred, [next(iter(g)) for g in gold])[1]
    precisions, recalls = [], []
    for i in range(n):
        same_cluster = [j for j in range(n) if pred[j] == pred[i]]
        sharing_gold = [j for j in range(n) if gold[j] & gold[i]]
        # Multiplicity precision: min(|C∩C'|, |L∩L'|) / |C∩C'|, and |C∩C'| = 1 here.
        precisions.append(
            sum(min(1, len(gold[i] & gold[j])) for j in same_cluster) / len(same_cluster)
        )
        # Multiplicity recall: min(|C∩C'|, |L∩L'|) / |L∩L'|.
        recalls.append(
            sum(
                min(int(pred[i] == pred[j]), len(gold[i] & gold[j])) / len(gold[i] & gold[j])
                for j in sharing_gold
            )
            / len(sharing_gold)
        )
    p, r = sum(precisions) / n, sum(recalls) / n
    return p, r, _f1(p, r)


def score(pred: list[int], gold_sets: list[set[str]], gold_primary: list[str]) -> Scores:
    if pred and all(len(g) == 1 for g in gold_sets):
        (pp, pr, pf), (bp, br, bf) = _partition_scores(pred, [next(iter(g)) for g in gold_sets])
    else:
        pp, pr, pf = pairwise(pred, gold_sets)
        bp, br, bf = bcubed(pred, gold_sets)
    ari = adjusted_rand_score(gold_primary, pred) if len(pred) > 1 else 1.0
    return Scores(
        pair_precision=pp,
        pair_recall=pr,
        pair_f1=pf,
        bcubed_precision=bp,
        bcubed_recall=br,
        bcubed_f1=bf,
        ari=float(ari),
        clusters=len(set(pred)),
        gold_groups=len(set(gold_primary)),
    )
