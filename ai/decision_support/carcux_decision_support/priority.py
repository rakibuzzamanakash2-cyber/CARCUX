"""Suggested priority from operational factors only (Spec §8.3).

What can hurt people or stop a city, how many, whether it is getting worse, how long
it has lasted, and how sure we are that it is real. Never who is involved or what
anyone said about anyone. Each factor adds points with a reason the analyst can read;
the analyst sets the priority, and whether they followed the suggestion is logged.

    score ≥ 8 → critical · ≥ 5 → high · ≥ 3 → medium · otherwise low
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from carcux_decision_support.model import SUPPORTING, EventFacts, type_label

# How directly the kind of event endangers life or stops movement and services.
HAZARD: dict[str, int] = {
    **dict.fromkeys(
        ["fire", "building_collapse", "explosion", "cyclone", "storm_surge", "flash_flood",
         "earthquake", "landslide"],
        3,
    ),
    **dict.fromkeys(
        ["flood", "river_erosion", "building_hazard", "road_accident", "rail_accident",
         "bridge_damage"],
        2,
    ),
}  # fmt: skip
DEFAULT_HAZARD = 1  # waterlogging, heavy rainfall, blockages, outages, closures
SERIOUS_DEPTH = frozenset({"waist-deep", "chest-deep", "above-head"})
PEOPLE_PER_HOUSEHOLD = 4  # a round, cautious figure for converting households
RECENT = timedelta(hours=2)
GROWING_REPORTS = 3
LONG_RUNNING = timedelta(hours=48)
LEVELS = ((8, "critical"), (5, "high"), (3, "medium"))


@dataclass(frozen=True)
class Factor:
    name: str
    points: int
    reason: str


@dataclass
class PrioritySuggestion:
    level: str  # critical, high, medium, low
    score: int
    factors: list[Factor] = field(default_factory=list)


def _level(score: int) -> str:
    return next((name for floor, name in LEVELS if score >= floor), "low")


def _people(value, unit: str | None) -> float:
    n = float(value)
    return n * PEOPLE_PER_HOUSEHOLD if unit and unit.startswith("household") else n


def _fmt(n: float) -> str:
    return f"{int(n):,}"


def suggest(event: EventFacts, now: datetime) -> PrioritySuggestion:
    if event.status in ("resolved", "dismissed"):
        why = "it is over" if event.status == "resolved" else "it was dismissed as not real"
        return PrioritySuggestion("low", 0, [Factor("status", 0, f"Low because {why}.")])

    f: list[Factor] = []
    kind = type_label(event.event_type)
    hazard = HAZARD.get(event.event_type, DEFAULT_HAZARD)
    f.append(Factor("hazard", hazard, f"A {kind}: hazard level {hazard} of 3."))

    deaths = event.estimate("casualty_count")
    if deaths is not None and float(deaths.value) > 0:
        n = float(deaths.value)
        f.append(Factor("deaths", 4 if n >= 10 else 2, f"About {_fmt(n)} dead."))

    affected = event.estimate("affected_count")
    if affected is not None:
        people = _people(affected.value, affected.unit)
        points = 3 if people >= 100_000 else 2 if people >= 10_000 else 1 if people >= 1000 else 0
        if points:
            f.append(Factor("affected", points, f"About {_fmt(people)} people affected."))

    depth = event.estimate("magnitude")
    if depth is not None and depth.value in SERIOUS_DEPTH:
        f.append(Factor("severity", 1, f"Water {depth.value}."))

    if event.family == "road_infrastructure":
        f.append(Factor("disruption", 1, "Stops movement or services while it lasts."))

    counted = [e for e in event.counted() if e.relation in SUPPORTING]
    recent = [e for e in counted if now - RECENT <= e.at <= now]
    if len(recent) >= GROWING_REPORTS:
        f.append(Factor("growing", 1, f"{len(recent)} new reports in the last 2 hours."))
    rose = _rising_deaths(event, now)
    if rose:
        f.append(Factor("rising", 1, rose))

    if event.ended_at is None and now - event.started_at >= LONG_RUNNING:
        days = (now - event.started_at).days
        f.append(Factor("duration", 1, f"Ongoing for {days} days."))

    doubt = _doubt(event, counted)
    if doubt:
        f.append(doubt)

    score = sum(x.points for x in f)
    return PrioritySuggestion(_level(score), score, f)


def _rising_deaths(event: EventFacts, now: datetime) -> str | None:
    """'Deaths rose from 23 to 52 in the last day' when credible counts went up."""
    said = sorted(
        (e.at, float(d.value))
        for e in event.counted()
        if e.relation in SUPPORTING
        for d in e.details
        if d.attribute == "casualty_count" and isinstance(d.value, int | float)
    )
    day_ago = now - timedelta(hours=24)
    before = [v for at, v in said if at < day_ago]
    since = [v for at, v in said if day_ago <= at <= now]
    if before and since and max(since) > max(before) * 1.2:
        return f"Deaths rose to {_fmt(max(since))} in the last day (from {_fmt(max(before))})."
    return None


def _doubt(event: EventFacts, counted) -> Factor | None:
    if event.assessment == "refuted" or event.suggested == "refuted":
        return Factor("confidence", -4, "Checked and found not to have happened.")
    if event.probability is not None and event.probability < 0.3:
        return Factor("confidence", -3, f"Likely not real ({event.probability:.0%} chance).")
    if len({e.key for e in counted}) <= 1:
        return Factor("confidence", -1, "Only one source so far.")
    return None
