"""A risk score per field-worker account: does its recent activity look unlike its own
history? A compromised account, or a worker under pressure, still logs in correctly.

Account-level only, for CARCUX's own field workers: no profiling of the public. The
score compares the account's last day with its earlier weeks, and each part of it comes
with a reason an admin can read. It marks an account for a conversation, never blocks it.

Parts (each 0–1; the score combines them as independent warnings, 1 − Π(1 − wᵢ·sᵢ)):

- **far**: recent reports are far from where the account usually reports, compared with
  how far it usually ranges;
- **rate**: many more reports than its usual day;
- **hours**: reports at hours when it almost never reports;
- **flagged**: the share of its recent reports with integrity flags (copied text, a
  mismatch between text and GPS, reused photos, impossible travel, bursts).
"""

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.extraction.places import haversine_km
from app.integrity.checks import Flag, Report

DHAKA = timezone(timedelta(hours=6))
RECENT = timedelta(hours=24)
MIN_HISTORY = 10  # fewer earlier reports than this: no baseline, flags only
WEIGHTS = {"far": 0.9, "rate": 0.6, "hours": 0.5, "flagged": 0.9}
REASON_FROM = 0.5  # a part this high is named as a reason


@dataclass
class AccountRisk:
    account: str
    score: float  # 0 (as usual) to 1
    parts: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    recent: int = 0
    baseline: int = 0


def _ramp(x: float, low: float, high: float) -> float:
    """0 at or below `low`, 1 at or above `high`, linear between."""
    return min(max((x - low) / (high - low), 0.0), 1.0)


def _poisson_tail(k: int, mean: float) -> float:
    """P(X ≥ k) for X ~ Poisson(mean)."""
    if k <= 0:
        return 1.0
    term = math.exp(-mean)
    below = term
    for i in range(1, k):
        term *= mean / i
        below += term
    return max(1.0 - below, 0.0)


def score(
    account: str,
    reports: list[Report],
    flags: dict[str, list[Flag]],
    now: datetime,
) -> AccountRisk:
    """The account's risk now, from its reports (any order) and each report's flags."""
    mine = sorted(
        (r for r in reports if r.account == account and r.received_at <= now),
        key=lambda r: r.received_at,
    )
    recent = [r for r in mine if r.received_at > now - RECENT]
    base = [r for r in mine if r.received_at <= now - RECENT]
    risk = AccountRisk(account, 0.0, recent=len(recent), baseline=len(base))
    if not recent:
        return risk
    parts: dict[str, float] = {}
    reasons: list[str] = []

    flagged = [r for r in recent if flags.get(r.id)]
    parts["flagged"] = _ramp(len(flagged) / len(recent), 0.1, 0.5)
    if parts["flagged"] >= REASON_FROM:
        codes = sorted({f.code for r in flagged for f in flags[r.id]})
        reasons.append(
            f"{len(flagged)} of {len(recent)} reports in the last day have "
            f"integrity flags ({', '.join(codes)})."
        )

    if len(base) >= MIN_HISTORY:
        home = (
            statistics.median(r.latitude for r in base),
            statistics.median(r.longitude for r in base),
        )
        spread = sorted(haversine_km(*home, r.latitude, r.longitude) for r in base)
        usual = max(spread[int(0.9 * (len(spread) - 1))], 2.0)  # its 90th percentile, ≥ 2 km
        away = statistics.median(haversine_km(*home, r.latitude, r.longitude) for r in recent)
        parts["far"] = _ramp(away / usual, 3.0, 10.0)
        if parts["far"] >= REASON_FROM:
            reasons.append(
                f"Reporting about {away:.0f} km from where it usually reports "
                f"(usually within {usual:.0f} km)."
            )

        days = max((base[-1].received_at - base[0].received_at).total_seconds() / 86400, 1.0)
        per_day = len(base) / days
        p = _poisson_tail(len(recent), per_day)
        parts["rate"] = _ramp(-math.log10(max(p, 1e-12)), 2.0, 6.0)
        if parts["rate"] >= REASON_FROM:
            reasons.append(
                f"{len(recent)} reports in the last day; it usually sends about "
                f"{per_day:.1f} a day."
            )

        by_hour = [0] * 24
        for r in base:
            by_hour[r.received_at.astimezone(DHAKA).hour] += 1
        rare = {h for h in range(24) if by_hour[h] / len(base) < 0.02}
        odd = [r for r in recent if r.received_at.astimezone(DHAKA).hour in rare]
        parts["hours"] = _ramp(len(odd) / len(recent), 0.2, 0.6)
        if parts["hours"] >= REASON_FROM:
            reasons.append(
                f"{len(odd)} of {len(recent)} recent reports at hours it almost never reports."
            )
    else:
        reasons.append(f"Only {len(base)} earlier reports: compared with its flags only.")

    keep = 1.0
    for name, s in parts.items():
        keep *= 1 - WEIGHTS[name] * s
    risk.score = round(1 - keep, 3)
    risk.parts = {k: round(v, 3) for k, v in parts.items()}
    risk.reasons = reasons
    return risk
