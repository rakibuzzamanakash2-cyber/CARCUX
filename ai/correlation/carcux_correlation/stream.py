"""Streaming evaluation for datasets too large for an all-pairs matrix.

`evaluate.py` builds an n x n x features array, which is fine for a few thousand
observations. A public benchmark has tens of thousands, so here each item is compared
only with the items before it, in blocks, and nothing quadratic is kept in memory. The
features and the clustering rule are the same as in `features.py` and `models.py`:

- the same eight pair features (`features.NAMES`), computed vectorised;
- the same methods (text, text+rules, joint and ablations);
- the same online average-linkage clustering, run for many thresholds in one pass so a
  threshold can be tuned on training data without re-reading the stream.

The protocol is train/test rather than cross-validation: a benchmark ships its own split.
"""

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass

import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from carcux_correlation import features as F
from carcux_correlation import models
from carcux_correlation.data import FAMILY, Obs
from carcux_correlation.metrics import Scores, bcubed, score

BLOCK = 512
COL = {name: k for k, name in enumerate(F.NAMES)}


def make_vectorizer(kind: str = "char") -> TfidfVectorizer:
    """`char`: character n-grams, as for short multilingual reports. `word`: words, the
    usual choice for full news articles."""
    if kind == "word":
        return TfidfVectorizer(sublinear_tf=True, min_df=2, max_df=0.5)
    return TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True, min_df=2)


@dataclass
class Stream:
    """Observations in time order, with what pair features need as arrays."""

    obs: list[Obs]
    vectors: sparse.csr_matrix  # L2-normalised TF-IDF rows
    hours: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    precision_km: np.ndarray
    located: np.ndarray
    type_code: np.ndarray  # -1 unknown
    family_code: np.ndarray  # -1 unknown
    gold: list[str]

    def __len__(self) -> int:
        return len(self.obs)


def build(obs: Sequence[Obs], vectorizer: TfidfVectorizer, max_chars: int | None = None) -> Stream:
    """`vectorizer` must already be fitted (on training data)."""
    obs = sorted(obs, key=lambda o: (o.time, o.obs_id))
    texts = [(o.text or "")[:max_chars].lower() for o in obs]
    vectors = sparse.csr_matrix(vectorizer.transform(texts), dtype=np.float32)
    t0 = obs[0].time if obs else None
    types = sorted({o.event_type for o in obs if o.event_type})
    families = sorted({FAMILY.get(t, t) for t in types})
    return Stream(
        obs=list(obs),
        vectors=vectors,
        hours=np.array([(o.time - t0).total_seconds() / 3600 for o in obs]),
        lat=np.array([o.lat if o.located else 0.0 for o in obs]),
        lon=np.array([o.lon if o.located else 0.0 for o in obs]),
        precision_km=np.array([(o.precision_m or 0) / 1000 for o in obs]),
        located=np.array([o.located for o in obs]),
        type_code=np.array([types.index(o.event_type) if o.event_type else -1 for o in obs]),
        family_code=np.array(
            [
                families.index(FAMILY.get(o.event_type, o.event_type)) if o.event_type else -1
                for o in obs
            ]
        ),
        gold=[o.primary for o in obs],
    )


def _haversine(lat1, lon1, lat2, lon2) -> np.ndarray:
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * F.EARTH_KM * np.arcsin(np.minimum(1.0, np.sqrt(a)))


def rows(s: Stream) -> Iterator[tuple[int, np.ndarray]]:
    """For each item i (in time order): the pair features against items 0..i-1,
    shape (i, len(NAMES)). Same values as `features.pair_features`."""
    n = len(s)
    for start in range(0, n, BLOCK):
        stop = min(start + BLOCK, n)
        cos_block = (s.vectors[start:stop] @ s.vectors[:stop].T).toarray()
        np.clip(cos_block, 0.0, 1.0, out=cos_block)
        for i in range(start, stop):
            f = np.zeros((i, len(F.NAMES)))
            if i == 0:
                yield i, f
                continue
            f[:, COL["text_cos"]] = cos_block[i - start, :i]
            both = s.located[i] & s.located[:i]
            if both.any():
                km = _haversine(s.lat[i], s.lon[i], s.lat[:i][both], s.lon[:i][both])
                spread = s.precision_km[i] + s.precision_km[:i][both]
                f[both, COL["both_located"]] = 1.0
                f[both, COL["log_km"]] = np.log1p(km)
                f[both, COL["log_scaled_km"]] = np.log1p(km / (1 + spread))
            f[:, COL["log_hours"]] = np.log1p(np.abs(s.hours[i] - s.hours[:i]))
            known = (s.type_code[i] >= 0) & (s.type_code[:i] >= 0)
            f[:, COL["same_type"]] = known & (s.type_code[:i] == s.type_code[i])
            f[:, COL["same_family"]] = known & (s.family_code[:i] == s.family_code[i])
            f[:, COL["type_unknown"]] = ~known
            yield i, f


# --- methods ------------------------------------------------------------------------


class Method:
    """Scores an item against the items before it, from their pair features."""

    name = "method"
    trainable = False

    def fit(self, x: np.ndarray, y: np.ndarray) -> "Method":
        return self

    def __call__(self, f: np.ndarray) -> np.ndarray:
        raise NotImplementedError


class Text(Method):
    name = "text"

    def __call__(self, f):
        return f[:, COL["text_cos"]]


class TextRules(Method):
    """B2, with the same rule as `models.TextThenRules`."""

    name = "text+rules"

    def __call__(self, f):
        out = f[:, COL["text_cos"]].copy()
        hours = np.expm1(f[:, COL["log_hours"]])
        out[hours > models.RULE_HOURS] = 0.0
        located = f[:, COL["both_located"]] == 1
        if located.any():
            km = np.expm1(f[:, COL["log_km"]])
            scaled = np.expm1(f[:, COL["log_scaled_km"]])
            # km / (1 + spread) = scaled, so spread = km / scaled - 1 where scaled > 0.
            spread = np.where(scaled > 0, km / np.maximum(scaled, 1e-12) - 1, 0.0)
            reach = models.RULE_KM + np.minimum(spread, models.MAX_REACH_KM)
            out[located & (km > reach)] = 0.0
        return out


class Joint(Method):
    trainable = True

    def __init__(self, drop: frozenset = frozenset(), label: str = "joint", C: float = 1.0):
        self.name = label
        self.cols = F.columns(set(drop))
        self.C = C
        self.model = None

    def fit(self, x, y):
        if len(set(y.tolist())) < 2:
            raise ValueError("training pairs need both classes")
        self.model = make_pipeline(
            StandardScaler(),
            LogisticRegression(C=self.C, class_weight="balanced", max_iter=1000),
        ).fit(x[:, self.cols], y)
        return self

    def __call__(self, f):
        if len(f) == 0:
            return np.zeros(0)
        return self.model.predict_proba(f[:, self.cols])[:, 1]

    def weights(self) -> dict[str, float]:
        lr = self.model[-1]
        return {F.NAMES[c]: float(w) for c, w in zip(self.cols, lr.coef_[0], strict=True)}


def methods() -> list[Method]:
    return [
        Text(),
        TextRules(),
        Joint(label="joint"),
        Joint(drop=frozenset(F.SPACE), label="joint-space"),
        Joint(drop=frozenset(F.TIME), label="joint-time"),
    ]


# --- training pairs ---------------------------------------------------------------------


def sample_pairs(s: Stream, *, per_item: int = 5, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Training pairs from a stream: for each item, up to `per_item` earlier items from
    its own event, `per_item` random earlier items from other events, and the
    `per_item` most text-similar earlier items from other events (hard negatives)."""
    rng = np.random.default_rng(seed)
    gold = np.array(s.gold)
    xs, ys = [], []
    for i, f in rows(s):
        if i == 0:
            continue
        same = np.flatnonzero(gold[:i] == gold[i])
        other = np.flatnonzero(gold[:i] != gold[i])
        empty = np.zeros(0, dtype=int)
        pos = rng.choice(same, min(per_item, len(same)), replace=False) if len(same) else empty
        neg = rng.choice(other, min(per_item, len(other)), replace=False) if len(other) else empty
        if len(other):
            cos = f[other, COL["text_cos"]]
            k = min(per_item, len(other))
            hard = other[np.argpartition(-cos, k - 1)[:k]]
            neg = np.union1d(neg, hard)
        # Fancy indexing copies, so the full row `f` is not kept alive.
        xs.append(f[np.concatenate([pos, neg]).astype(int)])
        ys.append(np.r_[np.ones(len(pos), dtype=int), np.zeros(len(neg), dtype=int)])
    if not xs:
        return np.zeros((0, len(F.NAMES))), np.zeros(0, dtype=int)
    return np.vstack(xs), np.concatenate(ys)


# --- clustering ---------------------------------------------------------------------------


def cluster(s: Stream, scorer: Callable[[np.ndarray], np.ndarray], thresholds) -> np.ndarray:
    """Online average-linkage clustering for every threshold at once.
    Returns labels with shape (len(thresholds), len(s))."""
    thresholds = np.asarray(thresholds, dtype=float)
    k, n = len(thresholds), len(s)
    labels = np.zeros((k, n), dtype=np.int64)
    n_clusters = np.zeros(k, dtype=np.int64)
    for i, f in rows(s):
        if i == 0:
            n_clusters[:] = 1
            continue
        sc = scorer(f)
        for t in range(k):
            lab = labels[t, :i]
            m = n_clusters[t]
            sums = np.bincount(lab, weights=sc, minlength=m)
            counts = np.bincount(lab, minlength=m)
            avg = sums / np.maximum(counts, 1)
            best = int(avg.argmax())
            if avg[best] >= thresholds[t]:
                labels[t, i] = best
            else:
                labels[t, i] = m
                n_clusters[t] += 1
    return labels


def candidate_thresholds(sample_scores: np.ndarray) -> np.ndarray:
    grid = np.linspace(0.02, 0.98, 25)
    if len(sample_scores):
        grid = np.concatenate([grid, np.quantile(sample_scores, np.linspace(0.02, 0.98, 25))])
    return np.unique(np.round(grid, 4))


@dataclass
class Outcome:
    method: str
    threshold: float
    train_bcubed_f1: float
    test: Scores
    weights: dict | None = None


def run(
    train: Stream,
    test: Stream,
    method_list: list[Method] | None = None,
    *,
    seed: int = 0,
    log: Callable[[str], None] = lambda m: None,
) -> list[Outcome]:
    """Fit on `train`, tune each method's threshold on `train` by B-cubed F1, then
    cluster `test` once and score it."""
    method_list = method_list if method_list is not None else methods()
    gold_train = [{g} for g in train.gold]
    x, y = sample_pairs(train, seed=seed)
    log(f"  training pairs: {len(y)} ({int(y.sum())} same-event)")
    outcomes = []
    for m in method_list:
        m.fit(x, y)
        cands = candidate_thresholds(m(x) if len(x) else np.zeros(0))
        labels = cluster(train, m, cands)
        f1s = [bcubed(labels[t].tolist(), gold_train)[2] for t in range(len(cands))]
        best = int(np.argmax(f1s))
        threshold = float(cands[best])
        pred = cluster(test, m, [threshold])[0].tolist()
        result = score(pred, [{g} for g in test.gold], test.gold)
        log(f"  {m.name:<12} threshold {threshold:.3f}  test B-cubed F1 {result.bcubed_f1:.3f}")
        outcomes.append(
            Outcome(
                method=m.name,
                threshold=threshold,
                train_bcubed_f1=float(f1s[best]),
                test=result,
                weights=m.weights() if isinstance(m, Joint) else None,
            )
        )
    return outcomes
