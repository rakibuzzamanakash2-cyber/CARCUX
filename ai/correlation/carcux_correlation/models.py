"""Scorers (how likely two observations describe the same event) and online clustering.

Methods compared (ai/correlation/README.md):

- B1 `text`: text similarity alone.
- B2 `text+rules`: text similarity, then the rule CARCUX uses today as a hard filter:
  within 5 km (widened by both locations' uncertainty, up to 300 km) and 48 hours.
  An item without a location is not filtered on place.
- `joint`: a logistic model over meaning, place, time and type together (proposed).
- `joint-space`, `joint-time`: the joint model without place or without time features
  (the ablations RQ1 needs).

Every scorer gives a matrix of pair scores in [0, 1]. Clustering is the same for all of
them, so differences come from the scores: observations arrive in time order; each
joins the existing cluster it is most similar to (average over the cluster's members)
if that similarity reaches a threshold, else it starts a new cluster. Thresholds are
chosen on training data only.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from carcux_correlation import features as F
from carcux_correlation.data import Obs
from carcux_correlation.metrics import bcubed

RULE_KM = 5.0
RULE_HOURS = 48.0
MAX_REACH_KM = 300.0


def gold_pairs(obs: Sequence[Obs], idx: Sequence[int]) -> tuple[list[tuple[int, int]], list[int]]:
    pairs, labels = [], []
    for a in range(len(idx)):
        for b in range(a + 1, len(idx)):
            i, j = idx[a], idx[b]
            pairs.append((i, j))
            labels.append(int(bool(obs[i].events & obs[j].events)))
    return pairs, labels


class Scorer:
    name = "scorer"

    def fit(self, obs: Sequence[Obs], feats: np.ndarray, idx: Sequence[int]) -> "Scorer":
        return self

    def scores(self, obs: Sequence[Obs], feats: np.ndarray, idx: Sequence[int]) -> np.ndarray:
        raise NotImplementedError


class TextOnly(Scorer):
    """B1."""

    name = "text"

    def scores(self, obs, feats, idx):
        sub = feats[np.ix_(idx, idx)]
        return sub[:, :, F.NAMES.index("text_cos")]


class TextThenRules(Scorer):
    """B2: text similarity, kept only where the current CARCUX place/time rule allows."""

    name = "text+rules"

    def scores(self, obs, feats, idx):
        out = TextOnly().scores(obs, feats, idx).copy()
        for a, i in enumerate(idx):
            for b, j in enumerate(idx):
                if a >= b:
                    continue
                oi, oj = obs[i], obs[j]
                hours = abs((oi.time - oj.time).total_seconds()) / 3600
                km = F.distance_km(oi, oj)
                reach = RULE_KM + min(
                    ((oi.precision_m or 0) + (oj.precision_m or 0)) / 1000, MAX_REACH_KM
                )
                if hours > RULE_HOURS or (km is not None and km > reach):
                    out[a, b] = out[b, a] = 0.0
        return out


@dataclass
class Joint(Scorer):
    """Proposed: a logistic model over meaning, place, time and type."""

    drop: frozenset = field(default_factory=frozenset)
    label: str = "joint"
    C: float = 1.0

    def __post_init__(self):
        self.name = self.label
        self.cols = F.columns(set(self.drop))
        self.model = None

    def fit(self, obs, feats, idx):
        pairs, labels = gold_pairs(obs, idx)
        if len(set(labels)) < 2:
            raise ValueError("training data needs both same-event and different-event pairs")
        x = np.array([feats[i, j, self.cols] for i, j in pairs])
        self.model = make_pipeline(
            StandardScaler(),
            LogisticRegression(C=self.C, class_weight="balanced", max_iter=1000),
        ).fit(x, labels)
        return self

    def scores(self, obs, feats, idx):
        n = len(idx)
        out = np.eye(n)
        if n < 2:
            return out
        a, b = np.triu_indices(n, k=1)
        x = feats[np.ix_(idx, idx)][a, b][:, self.cols]
        p = self.model.predict_proba(x)[:, 1]
        out[a, b] = out[b, a] = p
        return out

    def weights(self) -> dict[str, float]:
        """Standardised coefficients, for reading what the model relies on."""
        lr = self.model[-1]
        return {F.NAMES[c]: float(w) for c, w in zip(self.cols, lr.coef_[0], strict=True)}


def cluster(scores: np.ndarray, threshold: float, linkage: str = "average") -> list[int]:
    """Online: items in the given (time) order join the best cluster or start one."""
    labels: list[int] = []
    members: list[list[int]] = []
    for i in range(scores.shape[0]):
        best, best_s = -1, -1.0
        for c, m in enumerate(members):
            s = float(scores[i, m].mean() if linkage == "average" else scores[i, m].max())
            if s > best_s:
                best, best_s = c, s
        if best >= 0 and best_s >= threshold:
            members[best].append(i)
            labels.append(best)
        else:
            members.append([i])
            labels.append(len(members) - 1)
    return labels


def tune_threshold(scores: np.ndarray, gold: list[set[str]], linkage: str = "average") -> float:
    """The threshold with the best B-cubed F1 on training data."""
    upper = scores[np.triu_indices(scores.shape[0], k=1)]
    candidates = np.unique(
        np.concatenate([np.quantile(upper, np.linspace(0, 1, 41)), np.linspace(0.05, 0.95, 19)])
    )
    best_t, best_f = 0.5, -1.0
    for t in candidates:
        f = bcubed(cluster(scores, float(t), linkage), gold)[2]
        if f > best_f + 1e-12:
            best_t, best_f = float(t), f
    return best_t


def methods() -> list[Scorer]:
    return [
        TextOnly(),
        TextThenRules(),
        Joint(label="joint"),
        Joint(drop=frozenset(F.SPACE), label="joint-space"),
        Joint(drop=frozenset(F.TIME), label="joint-time"),
    ]
