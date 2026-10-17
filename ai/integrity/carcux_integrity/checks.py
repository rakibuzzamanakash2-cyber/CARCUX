"""Checks on one field report: things that look wrong even when the login is valid.

Flags mark a report for human review; they never block it. The first six are the
backend's rules (backend/app/services/integrity.py), here so the simulator and the
evaluation can run every check; the last two are new:

- `location_text_mismatch`: the text names a place, and the GPS position is far from
  every place it names (a phone somewhere else, or a report about somewhere else);
- `copied_text`: the text repeats a public post or another worker's report almost word
  for word (rumours re-entered as field reports, or one report sent from many accounts).
"""

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from carcux_extraction.places import find_places, haversine_km

MAX_PLAUSIBLE_SPEED_KMH = 150.0
MIN_DISTANCE_FOR_TRAVEL_KM = 2.0
FUTURE_TOLERANCE = timedelta(minutes=5)
OLD_OBSERVATION = timedelta(hours=24)
BURST_WINDOW = timedelta(minutes=10)
BURST_COUNT = 10
POOR_ACCURACY_M = 1000.0
SAME_PHOTO_BITS = 6  # the backend's near-duplicate photo threshold

# location_text_mismatch: how far beyond a named place's own uncertainty the GPS may be.
PLACE_MARGIN_KM = 5.0
CHECKED_LEVELS = frozenset({"locality", "upazila", "district"})  # a division is too wide
# copied_text: share of shared 4-character pieces, and the shortest text worth comparing.
# Against public posts; against other workers' reports only when long and near-identical,
# because two honest workers at the same place write alike ("Mirpur 10 e hatu pani"):
# that is corroboration, not copying.
COPY_SIMILARITY = 0.8
COPY_MIN_CHARS = 40
REPORT_COPY_SIMILARITY = 0.9
REPORT_COPY_MIN_CHARS = 80


@dataclass(frozen=True)
class Report:
    id: str
    account: str
    text: str
    latitude: float
    longitude: float
    observed_at: datetime
    received_at: datetime
    accuracy_m: float | None = None
    photo_hashes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Flag:
    code: str
    detail: str


@dataclass(frozen=True)
class Text:
    """A text to compare with: a public post or another report."""

    id: str
    text: str
    kind: str  # "public post" or "report"
    account: str | None = None


# --- The backend's rules ---------------------------------------------------------------


def timing(r: Report, now: datetime) -> list[Flag]:
    if r.observed_at > now + FUTURE_TOLERANCE:
        return [Flag("observed_in_future", "Observation time is in the future.")]
    if now - r.observed_at > OLD_OBSERVATION:
        hours = int((now - r.observed_at).total_seconds() // 3600)
        return [Flag("old_observation", f"Observed {hours} h before submission.")]
    return []


def accuracy(r: Report) -> list[Flag]:
    if r.accuracy_m is not None and r.accuracy_m > POOR_ACCURACY_M:
        return [Flag("poor_location_accuracy", f"GPS accuracy {r.accuracy_m:.0f} m.")]
    return []


def travel(r: Report, history: Iterable[Report]) -> list[Flag]:
    """Impossible travel against the same account's report closest in time."""
    mine = [h for h in history if h.account == r.account and h.id != r.id]
    if not mine:
        return []
    prev = min(mine, key=lambda h: abs((h.observed_at - r.observed_at).total_seconds()))
    km = haversine_km(prev.latitude, prev.longitude, r.latitude, r.longitude)
    hours = abs((r.observed_at - prev.observed_at).total_seconds()) / 3600
    if km <= MIN_DISTANCE_FOR_TRAVEL_KM:
        return []
    speed = km / hours if hours > 0 else math.inf
    if speed <= MAX_PLAUSIBLE_SPEED_KMH:
        return []
    shown = "instantly" if math.isinf(speed) else f"at {speed:.0f} km/h"
    return [Flag("impossible_travel", f"{km:.1f} km from report {prev.id} {shown}.")]


def burst(r: Report, history: Iterable[Report]) -> list[Flag]:
    recent = sum(
        1
        for h in history
        if h.account == r.account
        and h.id != r.id
        and r.received_at - BURST_WINDOW < h.received_at <= r.received_at
    )
    if recent >= BURST_COUNT:
        return [Flag("submission_burst", f"{recent + 1} reports in 10 minutes.")]
    return []


def _bits(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


def photos(r: Report, history: Iterable[Report]) -> list[Flag]:
    seen = [(h.id, p) for h in history if h.id != r.id for p in h.photo_hashes]
    out = []
    for i, mine in enumerate(r.photo_hashes, start=1):
        near = (rid for rid, p in seen if _bits(p, mine) <= SAME_PHOTO_BITS)
        hit = next(near, None)
        if hit is not None:
            out.append(Flag("photo_reused", f"Photo {i} matches a photo in report {hit}."))
    return out


# --- New: the text against the GPS, and copied text ------------------------------------


def location_text_mismatch(r: Report) -> list[Flag]:
    """The text names places, and the GPS is far from every one of them."""
    named = [p for p in find_places(r.text) if p.level in CHECKED_LEVELS]
    if not named:
        return []
    gps_km = (r.accuracy_m or 0.0) / 1000
    gaps = []
    for p in named:
        km = haversine_km(r.latitude, r.longitude, p.latitude, p.longitude)
        allowed = p.precision_m / 1000 + gps_km + PLACE_MARGIN_KM
        if km <= allowed:
            return []  # near at least one named place
        gaps.append((km - allowed, km, p))
    _, km, p = min(gaps, key=lambda g: g[0])
    return [
        Flag(
            "location_text_mismatch",
            f"The text names {p.surface} ({p.name}, {p.level}), but the GPS is {km:.0f} km away.",
        )
    ]


_NON_WORD = re.compile(r"[\W_]+", re.UNICODE)


def _pieces(text: str, n: int = 4) -> set[str]:
    t = _NON_WORD.sub(" ", text.casefold()).strip()
    return {t[i : i + n] for i in range(max(len(t) - n + 1, 0))}


def similarity(a: str, b: str) -> float:
    """Share of 4-character pieces the two texts have in common (Jaccard)."""
    pa, pb = _pieces(a), _pieces(b)
    return len(pa & pb) / len(pa | pb) if pa and pb else 0.0


def copied_text(r: Report, others: Iterable[Text]) -> list[Flag]:
    """Almost the same words as a public post, or another account's report."""
    length = len(r.text.strip())
    if length < COPY_MIN_CHARS:
        return []
    best, score = None, 0.0
    for o in others:
        if o.id == r.id or (o.kind == "report" and o.account == r.account):
            continue
        if o.kind == "report" and length < REPORT_COPY_MIN_CHARS:
            continue
        s = similarity(r.text, o.text)
        needed = REPORT_COPY_SIMILARITY if o.kind == "report" else COPY_SIMILARITY
        if s >= needed and s > score:
            best, score = o, s
    if best is None:
        return []
    return [Flag("copied_text", f"{score:.0%} the same words as {best.kind} {best.id}.")]


def check(
    r: Report,
    history: Iterable[Report] = (),
    texts: Iterable[Text] = (),
    now: datetime | None = None,
) -> list[Flag]:
    """Every check on one report. `history`: earlier reports from all accounts; `texts`:
    public posts and reports to compare its words with; `now`: when it arrived."""
    history = list(history)
    now = now or r.received_at
    return [
        *timing(r, now),
        *accuracy(r),
        *travel(r, history),
        *burst(r, history),
        *photos(r, history),
        *location_text_mismatch(r),
        *copied_text(r, texts),
    ]


@dataclass
class Checked:
    report: Report
    flags: list[Flag] = field(default_factory=list)
