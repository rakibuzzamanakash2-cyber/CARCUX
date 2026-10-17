"""Ways to turn an event's evidence into a probability that it happened.

Every method gives a raw score per event from the evidence published up to a cut-off;
a one-feature logistic (Platt) calibration fitted on training events turns the score
into a probability, the same way for every method, so differences come from the
scores. (Calibration itself is studied separately for RQ5.)

Baselines (README):

- **B3 `majority`:** share of items saying it happened (Laplace-smoothed).
- **B4 `equal`:** every item one equal vote: supports minus denials.
- **B5 `truthfinder`:** unsupervised truth discovery: source trust and event belief
  estimated together, iteratively, from the evidence alone (no labels).
- **`truthfinder-dep`:** the same, counting each copy cascade once.

Proposed:

- **`reliability-dep`:** each source's reliability learned from training events (how
  often its first-hand reports agreed with what really happened, shrunk towards its
  source type's rate). Copies are a separate channel: never counted as independent
  eyewitnesses, but who amplifies a claim still tells something (rumour accounts copy
  false claims), so copies count with each copier's own track record as a copier, and
  the calibration learns how much that channel weighs. Run with detected dependences,
  with the gold ones as an upper bound (`reliability-oracle`), with copies simply
  dropped (`reliability-dedup`), and without dependences (`reliability`), for RQ2.
"""

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from sklearn.linear_model import LogisticRegression

from carcux_fusion.data import Dataset, Event

Deps = dict[str, tuple[str, str]]


@dataclass(frozen=True)
class Vote:
    obs_id: str
    source_id: str
    source_type: str
    vote: int
    root: str  # the cascade's origin (itself when independent)


def votes(data: Dataset, event: Event, cutoff: datetime, deps: Deps | None) -> list[Vote]:
    """Evidence published by the cut-off, each with the origin of its copy cascade."""
    out = []
    for ev in event.evidence:
        ob = data.observations[ev.obs_id]
        if ob.published > cutoff:
            continue
        root, seen = ev.obs_id, set()
        while deps and root in deps and root not in seen:
            seen.add(root)
            root = deps[root][0]
        out.append(
            Vote(
                ev.obs_id, ob.source_id, data.source_type.get(ob.source_id, "other"), ev.vote, root
            )
        )
    return out


def independent(vs: list[Vote]) -> list[Vote]:
    """One vote per cascade: its origin's, if the origin is in view, else the earliest."""
    by_root: dict[str, Vote] = {}
    for v in vs:
        if v.root not in by_root or v.obs_id == v.root:
            by_root[v.root] = v
    return list(by_root.values())


def _logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


# --- Scorers ----------------------------------------------------------------------------


class Method:
    name = "method"
    uses_deps: str | None = None  # None, "detected" or "gold"

    def fit(self, data: Dataset, train: list[str], cutoffs: dict[str, datetime], deps: Deps):
        return self

    def raw(self, data: Dataset, events: Iterable[str], cutoffs, deps: Deps) -> dict[str, float]:
        raise NotImplementedError


class Majority(Method):
    name = "majority"

    def raw(self, data, events, cutoffs, deps):
        out = {}
        for eid in events:
            vs = votes(data, data.events[eid], cutoffs[eid], None)
            s = sum(v.vote > 0 for v in vs)
            out[eid] = _logit((s + 1) / (len(vs) + 2))
        return out


class Equal(Method):
    name = "equal"

    def raw(self, data, events, cutoffs, deps):
        return {
            eid: float(sum(v.vote for v in votes(data, data.events[eid], cutoffs[eid], None)))
            for eid in events
        }


class TruthFinder(Method):
    """Iterative trust estimation without labels (a TruthFinder / weighted-vote style
    scheme): belief in each event from its sources' trust, then each source's trust
    from how often it agrees with those beliefs, with a mild prior, until stable."""

    name = "truthfinder"

    def __init__(self, dependence: bool = False, iterations: int = 30):
        self.dependence = dependence
        self.iterations = iterations
        if dependence:
            self.name = "truthfinder-dep"
            self.uses_deps = "detected"

    def raw(self, data, events, cutoffs, deps):
        events = list(events)
        ev_votes = {}
        for eid in events:
            vs = votes(data, data.events[eid], cutoffs[eid], deps if self.dependence else None)
            ev_votes[eid] = independent(vs) if self.dependence else vs
        trust: dict[str, float] = defaultdict(lambda: 0.7)
        z = {}
        for _ in range(self.iterations):
            z = {
                eid: sum(v.vote * _logit(trust[v.source_id]) for v in vs)
                for eid, vs in ev_votes.items()
            }
            agree: dict[str, list[float]] = defaultdict(list)
            for eid, vs in ev_votes.items():
                p = 1 / (1 + math.exp(-max(-30, min(30, z[eid]))))
                for v in vs:
                    agree[v.source_id].append(p if v.vote > 0 else 1 - p)
            # Beta(3.5, 1.5) prior: sources are assumed mostly, not fully, right.
            trust = defaultdict(
                lambda: 0.7, {s: (sum(a) + 3.5) / (len(a) + 5.0) for s, a in agree.items()}
            )
        return z


class Reliability(Method):
    """Supervised source reliability.

    - `channels="all"` (no dependences): every item counts with its source's rate.
    - `channels="dedup"`: each copy cascade counts once, by its origin's source.
    - `channels="two"` (proposed): origins count with their sources' first-hand rate;
      copies form a second channel with each copier's own rate *as a copier* (how often
      what it passes on turns out true). The two sums are combined by the calibration
      fitted on training events, which learns how much copies should count.
    """

    def __init__(self, deps: str | None = "detected", channels: str = "two", strength: float = 3.0):
        self.uses_deps = deps
        self.channels = channels if deps else "all"
        self.strength = strength
        self.name = {
            ("all", None): "reliability",
            ("dedup", "detected"): "reliability-dedup",
            ("two", "detected"): "reliability-dep",
            ("two", "gold"): "reliability-oracle",
        }[(self.channels, deps)]

    def fit(self, data, train, cutoffs, deps):
        # Training events are over: learn from all of their evidence.
        first_hand: dict[str, list[int]] = defaultdict(list)
        passed_on: dict[str, list[int]] = defaultdict(list)
        by_type: dict[tuple[str, bool], list[int]] = defaultdict(list)
        self.type_of = dict(data.source_type)
        never = datetime.max.replace(tzinfo=_tz(data))
        for eid in train:
            event = data.events[eid]
            truth = 1 if event.occurred else -1
            for v in votes(data, event, never, deps if self.uses_deps else None):
                copy = self.channels != "all" and v.obs_id != v.root
                ok = int(v.vote == truth)
                (passed_on if copy else first_hand)[v.source_id].append(ok)
                by_type[(v.source_type, copy)].append(ok)
        self.type_rate = {k: (sum(a) + 1) / (len(a) + 2) for k, a in by_type.items()}
        self.rates = {}
        for copy, table in ((False, first_hand), (True, passed_on)):
            for s, a in table.items():
                prior = self.type_rate.get((self.type_of.get(s, "other"), copy), 0.6)
                self.rates[(s, copy)] = (sum(a) + self.strength * prior) / (len(a) + self.strength)
        return self

    def rate(self, source_id: str, copy: bool = False) -> float:
        if (source_id, copy) in self.rates:
            return self.rates[(source_id, copy)]
        return self.type_rate.get((self.type_of.get(source_id, "other"), copy), 0.6)

    def raw(self, data, events, cutoffs, deps):
        out = {}
        for eid in events:
            vs = votes(data, data.events[eid], cutoffs[eid], deps if self.uses_deps else None)
            if self.channels == "all":
                out[eid] = sum(v.vote * _logit(self.rate(v.source_id)) for v in vs)
                continue
            origins = independent(vs)
            origin_score = sum(v.vote * _logit(self.rate(v.source_id)) for v in origins)
            if self.channels == "dedup":
                out[eid] = origin_score
                continue
            kept = {v.obs_id for v in origins}
            copy_score = sum(
                v.vote * _logit(self.rate(v.source_id, copy=True))
                for v in vs
                if v.obs_id not in kept
            )
            out[eid] = (origin_score, copy_score)
        return out


def _tz(data: Dataset):
    first = next(iter(data.observations.values()), None)
    return first.published.tzinfo if first else None


def methods() -> list[Method]:
    from carcux_fusion.social import SocialSensing  # B7 (imports this module)

    return [
        Majority(),
        Equal(),
        TruthFinder(),
        TruthFinder(dependence=True),
        SocialSensing(),
        SocialSensing(dependence=True),
        SocialSensing(dependence=True, silence=False),
        SocialSensing(dependence=True, silence=False, supervised=True),
        Reliability(None),
        Reliability("detected", channels="dedup"),
        Reliability("detected"),
        Reliability("gold"),
    ]


# --- Calibration ----------------------------------------------------------------------------


def _matrix(scores) -> np.ndarray:
    x = np.asarray(scores, dtype=float)
    return x.reshape(-1, 1) if x.ndim == 1 else x


class Platt:
    """p = sigmoid(a . scores + b), fitted on training events. A method may give one
    score per event or several (the two-channel model gives two)."""

    def fit(self, scores, labels: list[int]) -> "Platt":
        x = _matrix(scores)
        y = np.asarray(labels)
        if len(set(y.tolist())) < 2:
            self.model = None
            self.base = float(y.mean()) if len(y) else 0.5
        else:
            self.model = LogisticRegression(C=100.0).fit(x, y)
        return self

    def predict(self, scores) -> np.ndarray:
        if self.model is None:
            return np.full(len(scores), self.base)
        return self.model.predict_proba(_matrix(scores))[:, 1]
