"""Pairwise evidence that two observations describe the same event: meaning, place, time.

- Meaning: cosine similarity of character n-gram TF-IDF vectors. Character n-grams
  work across Bangla script, Banglish and English spelling variation without a
  language-specific tokenizer; a multilingual sentence encoder can replace this later
  (`TextEncoder` is the seam).
- Place: great-circle distance, also scaled by both locations' uncertainty
  (`precision_m`): 20 km apart means little for two district-level news items and a
  lot for two GPS reports. Missing locations are flagged, never guessed.
- Time: hours between when each item says the situation was seen.
- Type: same claimed event type, same family, or unknown.
"""

import math
from collections.abc import Sequence

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from carcux_correlation.data import Obs

EARTH_KM = 6371.0088
NAMES = [
    "text_cos",
    "both_located",
    "log_km",
    "log_scaled_km",
    "log_hours",
    "same_type",
    "same_family",
    "type_unknown",
]
SPACE = {"both_located", "log_km", "log_scaled_km"}
TIME = {"log_hours"}
TEXT = {"text_cos"}


class TextEncoder:
    """Character n-gram TF-IDF, fitted on the texts it is asked to compare."""

    def __init__(self, ngram_range: tuple[int, int] = (2, 4)):
        self.ngram_range = ngram_range

    def similarity(self, texts: Sequence[str]) -> np.ndarray:
        cleaned = [t.lower() if t.strip() else "∅" for t in texts]
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=self.ngram_range, sublinear_tf=True)
        m = vec.fit_transform(cleaned)
        sim = (m @ m.T).toarray()
        np.fill_diagonal(sim, 1.0)
        return np.clip(sim, 0.0, 1.0)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_KM * math.asin(min(1.0, math.sqrt(a)))


def pair_features(a: Obs, b: Obs, text_cos: float) -> list[float]:
    if a.located and b.located:
        km = haversine_km(a.lat, a.lon, b.lat, b.lon)
        spread_km = ((a.precision_m or 0) + (b.precision_m or 0)) / 1000
        located, log_km, log_scaled = 1.0, math.log1p(km), math.log1p(km / (1 + spread_km))
    else:
        # Unknown place: neutral values, and the flag tells the model not to trust them.
        located, log_km, log_scaled = 0.0, 0.0, 0.0
    hours = abs((a.time - b.time).total_seconds()) / 3600
    known = a.event_type is not None and b.event_type is not None
    return [
        text_cos,
        located,
        log_km,
        log_scaled,
        math.log1p(hours),
        float(known and a.event_type == b.event_type),
        float(known and a.family == b.family),
        float(not known),
    ]


def distance_km(a: Obs, b: Obs) -> float | None:
    if not (a.located and b.located):
        return None
    return haversine_km(a.lat, a.lon, b.lat, b.lon)


def matrix(observations: Sequence[Obs], encoder: TextEncoder | None = None) -> np.ndarray:
    """Features for every pair: shape (n, n, len(NAMES)); symmetric."""
    n = len(observations)
    cos = (encoder or TextEncoder()).similarity([o.text for o in observations])
    out = np.zeros((n, n, len(NAMES)))
    for i in range(n):
        for j in range(i + 1, n):
            f = pair_features(observations[i], observations[j], float(cos[i, j]))
            out[i, j] = out[j, i] = f
    return out


def columns(drop: set[str] = frozenset()) -> list[int]:
    return [k for k, name in enumerate(NAMES) if name not in drop]
