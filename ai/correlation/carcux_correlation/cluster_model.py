"""Cluster-level joint model: does a new item join this cluster, or start a new one?

The pair-level joint model (`stream.Joint`, `models.Joint`) scores an item against each
earlier item and the clustering averages those scores. On the public news benchmark
that failed: stories run for weeks, the model learns that items far apart in time are
different events, so a new article looks unlike a long-running cluster's older members,
the average falls, and the story is split again and again (English: 222 stories became
1,159 clusters). The simulator hid this because simulated reports arrive within hours.

Here the decision is made against the cluster as a whole, with features that describe
the cluster, not each member:

- meaning: cosine to the cluster's centroid, and to its most similar member;
- time: hours since the cluster's newest member, and the cluster's age;
- size: log of the number of members;
- place: distance to the nearest located member (raw and scaled by uncertainty), with a
  flag for whether any located pair exists;
- type: share of type-known members with the same claimed type, or a flag if none.

It is trained on the same decision it makes: walking the training stream in time order
with the gold clusters, each item gives one positive (its own cluster, if it already
exists) and negatives (other clusters: random ones and the most text-similar ones).
All item-to-cluster features come from the pair features `stream.rows` already
computes, so the cost stays linear in the number of earlier items.
"""

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from carcux_correlation import stream
from carcux_correlation.stream import COL, Stream

NAMES = [
    "centroid_cos",
    "max_cos",
    "log_hours_newest",
    "log_hours_oldest",
    "log_size",
    "any_located",
    "log_min_km",
    "log_min_scaled_km",
    "same_type_share",
    "type_unknown",
    "cos_x_recency",
    "log_gap_ratio",
]
TEXT = {"centroid_cos", "max_cos"}
# Recency terms: a strong text match should tolerate a longer silence (cos_x_recency),
# and a silence means more for a story that usually updates hourly than for one that
# updates weekly (log_gap_ratio: hours since newest / the cluster's mean gap).
RECENCY = {"cos_x_recency", "log_gap_ratio"}
TIME = {"log_hours_newest", "log_hours_oldest"} | RECENCY
SPACE = {"any_located", "log_min_km", "log_min_scaled_km"}
TYPE = {"same_type_share", "type_unknown"}
STRUCTURE = {"log_size"}
NC = {name: k for k, name in enumerate(NAMES)}


class State:
    """One clustering in progress over a stream."""

    def __init__(self, n: int):
        self.labels = np.full(n, -1, dtype=np.int64)
        self.m = 0
        self.norm2 = np.zeros(n)  # squared norm of each cluster's vector sum
        self.newest = np.zeros(n)
        self.oldest = np.zeros(n)
        self.size = np.zeros(n)

    def add(self, i: int, c: int, hours: float, dot: float) -> None:
        """Put item i in cluster c (c == m opens a new one). `dot` is item i's dot product
        with the cluster's vector sum (0 for a new cluster)."""
        if c == self.m:
            self.m += 1
            self.oldest[c] = hours
        self.norm2[c] += 2 * dot + 1
        self.newest[c] = max(self.newest[c], hours) if self.size[c] else hours
        self.size[c] += 1
        self.labels[i] = c


TOP = 20  # candidate clusters scored per item


class Row:
    """Item i's pair features against earlier items, split into the columns the
    cluster features use. Built once per item and shared across thresholds."""

    __slots__ = ("cos", "located", "log_km", "log_scaled_km", "known", "same_type", "any_loc")

    def __init__(self, f: np.ndarray):
        self.cos = np.ascontiguousarray(f[:, COL["text_cos"]])
        self.located = f[:, COL["both_located"]] == 1
        self.any_loc = bool(self.located.any())
        self.log_km = np.ascontiguousarray(f[:, COL["log_km"]])
        self.log_scaled_km = np.ascontiguousarray(f[:, COL["log_scaled_km"]])
        self.known = 1.0 - f[:, COL["type_unknown"]]
        self.same_type = np.ascontiguousarray(f[:, COL["same_type"]])


def features(
    s: Stream, i: int, f: "np.ndarray | Row", st: State, clusters: np.ndarray | None = None
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Item i against open clusters. Returns (features for `clusters`, `clusters`, dot
    product of item i with every open cluster's vector sum).

    With `clusters=None` the candidates are the `TOP` clusters whose centroid is most
    similar in text (a retrieval step: a cluster sharing almost no text cannot
    plausibly be the right one, and scoring thousands of open clusters per item would
    make the benchmark take hours)."""
    m = st.m
    if m == 0:
        return np.zeros((0, len(NAMES))), np.zeros(0, dtype=int), np.zeros(0)
    r = f if isinstance(f, Row) else Row(f)
    lab = st.labels[:i]
    dot = np.bincount(lab, weights=r.cos, minlength=m)
    centroid = dot / np.sqrt(np.maximum(st.norm2[:m], 1e-12))
    if clusters is None:
        k = min(TOP, m)
        clusters = np.argpartition(-centroid, k - 1)[:k] if k < m else np.arange(m)
        clusters = clusters[np.argsort(-centroid[clusters], kind="stable")]  # best first
    clusters = np.asarray(clusters, dtype=int)
    k = len(clusters)
    pos = np.full(m, -1)
    pos[clusters] = np.arange(k)
    member = pos[lab]
    sel = member >= 0
    mpos = member[sel]

    out = np.zeros((k, len(NAMES)))
    out[:, NC["centroid_cos"]] = centroid[clusters]
    mx = np.zeros(k)
    np.maximum.at(mx, mpos, r.cos[sel])
    out[:, NC["max_cos"]] = mx
    out[:, NC["log_hours_newest"]] = np.log1p(np.maximum(s.hours[i] - st.newest[clusters], 0))
    out[:, NC["log_hours_oldest"]] = np.log1p(np.maximum(s.hours[i] - st.oldest[clusters], 0))
    out[:, NC["log_size"]] = np.log(st.size[clusters])
    since = np.maximum(s.hours[i] - st.newest[clusters], 0)
    span = st.newest[clusters] - st.oldest[clusters]
    mean_gap = span / np.maximum(st.size[clusters] - 1, 1)
    out[:, NC["cos_x_recency"]] = out[:, NC["centroid_cos"]] * out[:, NC["log_hours_newest"]]
    out[:, NC["log_gap_ratio"]] = np.log1p(since / (mean_gap + 1.0))
    if r.any_loc:
        located = r.located[sel]
        if located.any():
            lpos = mpos[located]
            any_loc = np.bincount(lpos, minlength=k) > 0
            for name, values in (("log_min_km", r.log_km), ("log_min_scaled_km", r.log_scaled_km)):
                best = np.full(k, np.inf)
                np.minimum.at(best, lpos, values[sel][located])
                out[:, NC[name]] = np.where(any_loc, best, 0.0)
            out[:, NC["any_located"]] = any_loc
    n_known = np.bincount(mpos, weights=r.known[sel], minlength=k)
    n_same = np.bincount(mpos, weights=r.same_type[sel], minlength=k)
    out[:, NC["same_type_share"]] = n_same / np.maximum(n_known, 1)
    out[:, NC["type_unknown"]] = n_known == 0
    return out, clusters, dot


class ClusterJoint:
    """Logistic model over item-to-cluster features."""

    def __init__(
        self,
        drop: frozenset = frozenset(),
        label: str = "cjoint",
        C: float = 1.0,
        per_item: int = 5,
    ):
        self.name = label
        self.cols = [k for k, n in enumerate(NAMES) if n not in drop]
        self.C = C
        self.per_item = per_item
        self._w = None

    # Training ----------------------------------------------------------------------------

    def training_data(self, s: Stream, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
        rng = np.random.default_rng(seed)
        st = State(len(s))
        cluster_of: dict[str, int] = {}
        xs, ys = [], []
        for i, f in stream.rows(s):
            own = cluster_of.get(s.gold[i])
            if st.m:
                # Negatives as the model will meet them: the retrieved candidates
                # (hard), plus a few random open clusters.
                _, cands, dot = features(s, i, f, st)
                hard = cands[cands != own][: self.per_item * 2]
                taken = np.r_[hard, [own] if own is not None else []]
                others = np.setdiff1d(np.arange(st.m), taken)
                rand = rng.choice(others, min(self.per_item, len(others)), replace=False)
                picked = np.r_[[own] if own is not None else [], hard, rand].astype(int)
                x, _, _ = features(s, i, f, st, clusters=picked)
                xs.append(x)
                ys.append(np.r_[[1] if own is not None else [], np.zeros(len(hard) + len(rand))])
            c = own if own is not None else st.m
            st.add(i, c, s.hours[i], float(dot[c]) if own is not None else 0.0)
            cluster_of.setdefault(s.gold[i], c)
        if not xs:
            return np.zeros((0, len(NAMES))), np.zeros(0, dtype=int)
        return np.vstack(xs), np.concatenate(ys).astype(int)

    def fit(self, s: Stream, seed: int = 0) -> "ClusterJoint":
        x, y = self.training_data(s, seed)
        if len(set(y.tolist())) < 2:
            raise ValueError("training stream needs both join and new-cluster decisions")
        x = x[:, self.cols]
        scaler = StandardScaler().fit(x)
        lr = LogisticRegression(C=self.C, class_weight="balanced", max_iter=2000)
        lr.fit(scaler.transform(x), y)
        scale = np.where(scaler.scale_ > 0, scaler.scale_, 1.0)
        self._w = (scaler.mean_, scale, lr.coef_[0], float(lr.intercept_[0]))
        self.n_train = len(y)
        return self

    def prob(self, x: np.ndarray) -> np.ndarray:
        mean, scale, coef, b = self._w
        z = ((x[:, self.cols] - mean) / scale) @ coef + b
        return 1.0 / (1.0 + np.exp(-np.clip(z, -50, 50)))

    def weights(self) -> dict[str, float]:
        return {NAMES[c]: float(w) for c, w in zip(self.cols, self._w[2], strict=True)}

    # Clustering --------------------------------------------------------------------------

    def cluster(self, s: Stream, thresholds) -> np.ndarray:
        """Online clustering for every threshold at once: labels (len(thresholds), n)."""
        thresholds = np.asarray(thresholds, dtype=float)
        states = [State(len(s)) for _ in thresholds]
        for i, f in stream.rows(s):
            row = Row(f)
            for t, st in enumerate(states):
                if st.m:
                    x, cands, dot = features(s, i, row, st)
                    p = self.prob(x)
                    best = int(p.argmax())
                    if p[best] >= thresholds[t]:
                        c = int(cands[best])
                        st.add(i, c, s.hours[i], float(dot[c]))
                        continue
                st.add(i, st.m, s.hours[i], 0.0)
        return np.array([st.labels for st in states])


def methods(with_space: bool = True, with_recency_ablation: bool = False) -> list[ClusterJoint]:
    """`ctext`: the same cluster-level model with meaning only (the fair text baseline).
    `cjoint`: meaning, place, time, type and size. Ablations drop place or time, and
    optionally only the recency terms (`cjoint-recency`, the October 2026 first version)."""
    no_text = TIME | SPACE | TYPE
    out = [
        ClusterJoint(drop=frozenset(no_text), label="ctext"),
        ClusterJoint(label="cjoint"),
    ]
    if with_space:
        out.append(ClusterJoint(drop=frozenset(SPACE), label="cjoint-space"))
    out.append(ClusterJoint(drop=frozenset(TIME), label="cjoint-time"))
    if with_recency_ablation:
        out.append(ClusterJoint(drop=frozenset(RECENCY), label="cjoint-recency"))
    return out
