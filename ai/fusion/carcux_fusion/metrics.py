"""How good and how honest a probability that an event happened is (RQ5).

- Brier score: mean squared error of the probability (lower is better).
- Log loss: penalises confident mistakes heavily.
- Expected calibration error (ECE): in bins of predicted probability, the average gap
  between what was predicted and how often events really happened (10 equal-width
  bins, weighted by bin size).
- Adaptive ECE: the same with equal-count bins (steadier on small sets, where
  equal-width bins can be almost empty).
- Bias: mean prediction minus how often events happened (positive: too sure that
  things happened overall).
- Accuracy at 0.5, and AUC (ranking: are real events given higher probabilities?).
"""

from dataclasses import dataclass

import numpy as np
from sklearn.metrics import roc_auc_score

EPS = 1e-6


@dataclass(frozen=True)
class Scores:
    brier: float
    log_loss: float
    ece: float
    accuracy: float
    auc: float | None
    n: int

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def ece(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    which = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    total = 0.0
    for b in range(bins):
        inside = which == b
        if inside.any():
            total += inside.mean() * abs(p[inside].mean() - y[inside].mean())
    return float(total)


def ece_adaptive(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    p, y = np.asarray(p, dtype=float), np.asarray(y, dtype=float)
    if len(p) == 0:
        return 0.0
    order = np.argsort(p, kind="stable")
    total = 0.0
    for part in np.array_split(order, min(bins, len(p))):
        total += len(part) / len(p) * abs(p[part].mean() - y[part].mean())
    return float(total)


def reliability(p: np.ndarray, y: np.ndarray, bins: int = 10) -> list[dict]:
    """Per-bin mean prediction and observed frequency, for a reliability diagram."""
    edges = np.linspace(0, 1, bins + 1)
    which = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    return [
        {
            "bin": [float(edges[b]), float(edges[b + 1])],
            "n": int((which == b).sum()),
            "predicted": float(p[which == b].mean()) if (which == b).any() else None,
            "observed": float(y[which == b].mean()) if (which == b).any() else None,
        }
        for b in range(bins)
    ]


def score(p, y) -> Scores:
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    y = np.asarray(y, dtype=float)
    auc = float(roc_auc_score(y, p)) if len(set(y.tolist())) == 2 else None
    return Scores(
        brier=float(np.mean((p - y) ** 2)),
        log_loss=float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))),
        ece=ece(p, y),
        accuracy=float(np.mean((p >= 0.5) == (y == 1))),
        auc=auc,
        n=len(y),
    )
