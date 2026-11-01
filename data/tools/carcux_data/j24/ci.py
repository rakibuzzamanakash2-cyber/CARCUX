"""Percentile bootstrap confidence intervals, resampling whole units (claims or pairs)."""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence

REPS, SEED = 2000, 2024


def interval(units: Sequence, stat: Callable[[list], float | None], *, reps: int = REPS,
             level: float = 0.95) -> list[float] | None:  # fmt: skip
    """[low, high] of `stat` over resamples of `units`; None when it cannot be computed."""
    if len(units) < 2:
        return None
    rng = random.Random(SEED)  # noqa: S311 - reproducible resampling, not security
    values = []
    for _ in range(reps):
        v = stat([units[rng.randrange(len(units))] for _ in units])
        if v is not None:
            values.append(v)
    if len(values) < reps / 2:
        return None
    values.sort()
    lo = values[int((1 - level) / 2 * len(values))]
    hi = values[min(len(values) - 1, int((1 + level) / 2 * len(values)))]
    return [round(lo, 4), round(hi, 4)]
