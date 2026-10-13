"""Details in dispute (RQ3): do reports that agree an event happened disagree on how
bad it was, how many were affected or died, or why?

For one event, from the reports published by a cut-off:

- **claims per detail**, one per copy cascade (a copy repeats its origin's numbers, so
  it is not a second opinion), each weighted by its source's learned reliability;
- **disputed**: two credible claims (sources with a learned reliability of at least
  0.5) disagree. Counts are compared with a tolerance: an affected count within 25 %
  agrees; deaths must match exactly;
- **best estimate**: weighted mode (magnitude, cause) or weighted median (counts).

Value estimation is compared across four strategies: the first report's value, the
most common value over every item (copies included), over one item per cascade, and
over one per cascade weighted by reliability (proposed).
"""

import math
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from carcux_fusion.data import DETAILS, Dataset, Event
from carcux_fusion.methods import Deps, independent, votes

AFFECTED_TOLERANCE = 0.25
NUMERIC = {"affected_count", "casualty_count"}
CREDIBLE_RATE = 0.5


def agrees(detail: str, a, b) -> bool:
    if detail == "affected_count":
        return abs(a - b) <= AFFECTED_TOLERANCE * max(a, b, 1)
    return a == b


@dataclass(frozen=True)
class Claim:
    detail: str
    value: object
    weight: float  # log-odds that the source is right, floored
    rate: float
    obs_id: str
    published: datetime
    annotated_wrong: bool  # the link's `conflicts` names this detail


def claims(
    data: Dataset,
    event: Event,
    cutoff: datetime,
    deps: Deps | None,
    rate: Callable[[str], float] = lambda s: 0.6,
    *,
    one_per_cascade: bool = True,
) -> dict[str, list[Claim]]:
    """Every detail claimed by the reports in view (supporting reports only)."""
    vs = [v for v in votes(data, event, cutoff, deps) if v.vote > 0]
    if one_per_cascade:
        vs = independent(vs)
    wrong = {e.obs_id: e.conflicts for e in event.evidence}
    out: dict[str, list[Claim]] = defaultdict(list)
    for v in vs:
        ob = data.observations[v.obs_id]
        r = rate(v.source_id)
        for detail, value in ob.claims.items():
            out[detail].append(
                Claim(
                    detail=detail,
                    value=value,
                    weight=max(math.log(r / (1 - r)), 0.01) if 0 < r < 1 else 0.01,
                    rate=r,
                    obs_id=v.obs_id,
                    published=ob.published,
                    annotated_wrong=detail in wrong.get(v.obs_id, ()),
                )
            )
    return out


def disputed(cs: list[Claim]) -> bool:
    credible = [c for c in cs if c.rate >= CREDIBLE_RATE]
    return any(not agrees(a.detail, a.value, b.value) for a in credible for b in credible)


def disputed_annotated(cs: list[Claim]) -> bool:
    """From annotators' `conflicts`: a credible claim marked wrong and another marked
    right (the upper bound for detection)."""
    credible = [c for c in cs if c.rate >= CREDIBLE_RATE]
    return any(c.annotated_wrong for c in credible) and any(not c.annotated_wrong for c in credible)


def estimate(cs: list[Claim], weighted: bool = True):
    if not cs:
        return None
    weights = [c.weight if weighted else 1.0 for c in cs]
    if cs[0].detail in NUMERIC:
        pairs = sorted(zip((c.value for c in cs), weights, strict=True))
        half, acc = sum(weights) / 2, 0.0
        for value, w in pairs:
            acc += w
            if acc >= half:
                return value
        return pairs[-1][0]
    totals: dict = defaultdict(float)
    for c, w in zip(cs, weights, strict=True):
        totals[c.value] += w
    return max(
        totals, key=lambda v: (totals[v], -min(c.published.timestamp() for c in cs if c.value == v))
    )


def estimates(
    data: Dataset, event: Event, cutoff: datetime, deps: Deps, rate: Callable[[str], float]
) -> dict[str, dict[str, object]]:
    """Each strategy's estimate of each claimed detail."""
    every = claims(data, event, cutoff, deps, rate, one_per_cascade=False)
    once = claims(data, event, cutoff, deps, rate)
    out: dict[str, dict[str, object]] = {}
    for detail in DETAILS:
        if not every.get(detail):
            continue
        out[detail] = {
            "first": min(every[detail], key=lambda c: (c.published, c.obs_id)).value,
            "majority": estimate(every[detail], weighted=False),
            "independent": estimate(once[detail], weighted=False),
            "weighted": estimate(once[detail], weighted=True),
        }
    return out
