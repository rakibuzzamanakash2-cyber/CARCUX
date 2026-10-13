"""Which observations are copies of earlier ones (the `dependences` the fusion needs).

For every observation about an event, compared with the earlier ones about the same
event:

- **text overlap:** character n-gram TF-IDF cosine (Bangla, Banglish and English alike);
  a copy (verbatim, reposted, reworded) shares most of its origin's text;
- **attribution:** phrases such as "according to", "er moto", "এর মতে", "sharing",
  "RT", which mark an item as passing on someone else's report;
- **reused media:** perceptual hashes within a few bits of an earlier item's;
- **order:** only an earlier item can be the origin.

An item is a copy if its most similar earlier item reaches a text threshold (tuned on
training events), or it reuses an earlier item's photo, or it attributes and is close
enough in text to name an origin. The origin is that earlier item.

Limits worth stating: two eyewitnesses writing near-identical sentences would look like
a copy, and a copy that rewrites everything would be missed. Simulated copies follow
the simulator's own phrasing, so detection there is optimistic; real CARCUX-BD
dependences are the real test.
"""

import re
from dataclasses import dataclass

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from carcux_fusion.data import Dataset

ATTRIBUTION = re.compile(
    r"according to|reported by|\bvia\b|\bRT\b|sharing:|shared from|"
    r"er moto|theke jana|share korlam|"
    r"এর মতে|সূত্রে|জানিয়েছে|শেয়ার করছি",
    re.IGNORECASE,
)
MEDIA_BITS = 6  # perceptual hashes this close are the same picture
ATTRIBUTION_FLOOR = 0.3  # an attributing item still needs this much text in common


def hamming(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


@dataclass(frozen=True)
class Candidate:
    obs_id: str
    origin: str
    text_cos: float
    attributes: bool
    same_media: bool


class Detector:
    def __init__(self, data: Dataset, threshold: float = 0.6):
        self.data = data
        self.threshold = threshold
        ids = list(data.observations)
        self.index = {oid: k for k, oid in enumerate(ids)}
        texts = [data.observations[o].text.lower() or "∅" for o in ids]
        self.vectors = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True
        ).fit_transform(texts)
        self._candidates: dict[str, list[Candidate]] = {}

    def candidates(self, event_id: str) -> list[Candidate]:
        """For each item of the event after the first: its best earlier match."""
        if event_id in self._candidates:
            return self._candidates[event_id]
        obs = [self.data.observations[e.obs_id] for e in self.data.events[event_id].evidence]
        obs.sort(key=lambda o: (o.published, o.obs_id))
        out = []
        if len(obs) > 1:
            m = self.vectors[[self.index[o.obs_id] for o in obs]]
            sim = (m @ m.T).toarray()
            for j in range(1, len(obs)):
                earlier = [i for i in range(j) if obs[i].published <= obs[j].published]
                if not earlier:
                    continue
                media = [
                    i
                    for i in earlier
                    if any(
                        hamming(a, b) <= MEDIA_BITS for a in obs[j].phashes for b in obs[i].phashes
                    )
                ]
                best = max(earlier, key=lambda i: sim[j, i])
                origin = media[-1] if media else best
                out.append(
                    Candidate(
                        obs_id=obs[j].obs_id,
                        origin=obs[origin].obs_id,
                        text_cos=float(sim[j, best]),
                        attributes=bool(ATTRIBUTION.search(obs[j].text)),
                        same_media=bool(media),
                    )
                )
        self._candidates[event_id] = out
        return out

    def is_copy(self, c: Candidate, threshold: float | None = None) -> bool:
        t = self.threshold if threshold is None else threshold
        return (
            c.same_media
            or c.text_cos >= t
            or (c.attributes and c.text_cos >= min(t, ATTRIBUTION_FLOOR))
        )

    def detect(self, event_ids, threshold: float | None = None) -> dict[str, tuple[str, str]]:
        out = {}
        for eid in event_ids:
            for c in self.candidates(eid):
                if self.is_copy(c, threshold):
                    kind = (
                        "same_media" if c.same_media else ("cites" if c.attributes else "rewrite")
                    )
                    out[c.obs_id] = (c.origin, kind)
        return out

    def tune(self, event_ids, grid=None) -> float:
        """The text threshold with the best item-level F1 against gold dependences."""
        grid = np.round(np.arange(0.3, 0.96, 0.05), 2) if grid is None else grid
        best_t, best_f = self.threshold, -1.0
        for t in grid:
            f = score(self.detect(event_ids, float(t)), self.data, event_ids)["f1"]
            if f > best_f + 1e-12:
                best_t, best_f = float(t), f
        self.threshold = best_t
        return best_t


def score(predicted: dict, data: Dataset, event_ids) -> dict:
    """Item level: is each item correctly flagged as a copy, and when it is, does the
    predicted origin lie in the same copy cascade as the true one?"""
    items = {e.obs_id for eid in event_ids for e in data.events[eid].evidence}
    gold = {o for o in data.dependences if o in items}
    pred = {o for o in predicted if o in items}
    tp = len(gold & pred)
    p = tp / len(pred) if pred else 1.0
    r = tp / len(gold) if gold else 1.0
    f1 = 0.0 if p + r == 0 else 2 * p * r / (p + r)

    def root(o: str) -> str:
        seen = set()
        while o in data.dependences and o not in seen:
            seen.add(o)
            o = data.dependences[o][0]
        return o

    right_origin = sum(root(predicted[o][0]) == root(o) for o in gold & pred)
    return {
        "precision": p,
        "recall": r,
        "f1": f1,
        "origin_in_cascade": right_origin / tp if tp else None,
        "gold_copies": len(gold),
        "predicted_copies": len(pred),
    }
