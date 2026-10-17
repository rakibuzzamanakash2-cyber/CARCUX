"""B7: truth discovery from social sensing (Wang et al.), the closest prior work to
CARCUX's fusion (research gap note, October 2026).

**B7a `socialsensing`** follows Wang, Kaplan, Le and Abdelzaher, "On truth discovery
in social sensing: a maximum likelihood estimation approach" (IPSN 2012). Each event is
a binary claim, true or false. Each source has an unknown behaviour when a claim is
true and when it is false. Expectation-maximisation estimates those behaviours and each
claim's truth together, without labels. The original model has one kind of report (a
source makes the claim or stays silent). CARCUX evidence can also deny, so each
source-event pair has three outcomes here: supports, denies, or silent. That is the
natural extension, and with no denials it reduces to the original.

**B7 `socialsensing-dep`** adds the dependence model of Wang et al., "Using humans as
sensors: an estimation-theoretic perspective" (IPSN 2014). When a source repeats a claim
its parent (the source it copied) also made, the repeat follows the parent with a
"repeat ratio" that does not depend on the truth, so it carries no information and
drops out of the likelihood. A copy whose origin is not in view counts as independent.
Copies come from the same detected dependences as CARCUX's own methods.

Silence: as in the original, a source that spoke about other events in the batch but
not about this one is counted as silent on it (`silence=True`). With `silence=False`
only sources that spoke about the event count.

Like B5, the method is unsupervised and runs over every event in view (training and
held-out events, without their labels); its log posterior odds are the raw score, and
the shared Platt calibration turns it into a probability.

**`-sup`**: the same model given what CARCUX's own method gets, the outcomes of the
training events. Their truth is held fixed during expectation-maximisation, so source
behaviours are learned from known outcomes as well as from agreement. This answers
"is CARCUX better only because it sees labels?".
"""

from datetime import datetime

import numpy as np

from carcux_fusion.data import Dataset
from carcux_fusion.methods import Method, votes

SUPPORT, DENY, SILENT = 0, 1, 2


class SocialSensing(Method):
    def __init__(
        self,
        dependence: bool = False,
        silence: bool = True,
        iterations: int = 100,
        smoothing: float = 1.0,
        supervised: bool = False,
    ):
        self.dependence = dependence
        self.silence = silence
        self.iterations = iterations
        self.smoothing = smoothing
        self.supervised = supervised  # Method.supervised: cross-fitted calibration
        self.known: dict[str, bool] = {}
        self.name = "socialsensing-dep" if dependence else "socialsensing"
        if not silence:
            self.name += "-nosilence"
        if supervised:
            self.name += "-sup"
        self.uses_deps = "detected" if dependence else None

    def fit(self, data, train, cutoffs, deps):
        self.known = {e: data.events[e].occurred for e in train} if self.supervised else {}
        return self

    def observations(
        self, data: Dataset, events: list[str], cutoffs: dict[str, datetime], deps
    ) -> tuple[list[str], np.ndarray, np.ndarray]:
        """Sources, an outcome matrix (sources x events) and a mask of the pairs that
        count. A source's latest vote on an event stands for it."""
        latest: dict[tuple[str, int], int] = {}  # (source, event index) -> vote
        for j, eid in enumerate(events):
            vs = votes(data, data.events[eid], cutoffs[eid], deps if self.dependence else None)
            in_view = {v.obs_id for v in vs}
            for v in vs:  # in publication order, so the latest vote wins
                if self.dependence and deps.get(v.obs_id, (None,))[0] in in_view:
                    # The copied observation is in view: the repeat says nothing about
                    # the truth (Wang et al. 2014).
                    continue
                latest[(v.source_id, j)] = v.vote
        sources = sorted({s for s, _ in latest})
        row = {s: i for i, s in enumerate(sources)}
        x = np.full((len(sources), len(events)), SILENT, dtype=int)
        mask = np.zeros((len(sources), len(events)), dtype=bool)
        for (s, j), vote in latest.items():
            x[row[s], j] = SUPPORT if vote > 0 else DENY
            mask[row[s], j] = True
        if self.silence:
            mask[:] = True
        return sources, x, mask

    def raw(self, data, events, cutoffs, deps):
        events = list(events)
        _, x, mask = self.observations(data, events, cutoffs, deps)
        if x.size == 0:
            return {eid: 0.0 for eid in events}
        onehot = np.stack([(x == k) & mask for k in (SUPPORT, DENY, SILENT)])  # 3 x S x E
        # Start from the share of supporting voices, so the reading "sources mostly
        # tell the truth" is the one expectation-maximisation climbs from.
        sup, den = onehot[SUPPORT].sum(0), onehot[DENY].sum(0)
        q = (sup + 1.0) / (sup + den + 2.0)
        fixed = np.array([eid in self.known for eid in events])
        truth = np.array([float(self.known.get(eid, 0)) for eid in events])
        q = np.where(fixed, truth, q)
        a = self.smoothing
        z = np.zeros(len(events))
        for _ in range(self.iterations):
            # M-step: each source's outcome rates when claims are true and when false.
            wt, wf = q[None, :], (1 - q)[None, :]
            pt = (onehot * wt).sum(2) + a  # 3 x S
            pf = (onehot * wf).sum(2) + a
            pt /= pt.sum(0, keepdims=True)
            pf /= pf.sum(0, keepdims=True)
            d = float(np.clip(q.mean(), 1e-3, 1 - 1e-3))
            # E-step: log odds of each claim being true.
            llr = np.log(pt) - np.log(pf)  # 3 x S
            z = np.log(d / (1 - d)) + np.einsum("ks,kse->e", llr, onehot)
            q_new = np.where(fixed, truth, 1 / (1 + np.exp(-np.clip(z, -30, 30))))
            if np.max(np.abs(q_new - q)) < 1e-6:
                q = q_new
                break
            q = q_new
        return {eid: float(z[j]) for j, eid in enumerate(events)}
