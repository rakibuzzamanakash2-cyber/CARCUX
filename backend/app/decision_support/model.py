"""What decision support reads: an event and its evidence, as plain values.

The backend fills these from its database; tests and the evaluation fill them by hand.
Nothing here names a person: sources are outlets, pages or "A field worker", and the
priority never depends on who is involved (Spec §8.3).
"""

from dataclasses import dataclass, field
from datetime import datetime

SUPPORTING = frozenset({"supports", "partially_supports"})
COUNTS = frozenset({"casualty_count", "affected_count"})


@dataclass(frozen=True)
class Detail:
    """A detail an item states: deaths, people affected, depth, cause, status."""

    attribute: str
    value: object
    unit: str | None = None
    surface: str = ""  # the words it came from


@dataclass(frozen=True)
class Evidence:
    """One item linked to the event. `id` is what summaries cite."""

    id: str
    source: str  # display name: the outlet, the page, or "A field worker"
    kind: str  # field, news, social, official, alert …
    relation: str  # supports, partially_supports, contradicts, related, unrelated
    at: datetime  # when it was said (received or published)
    headline: str = ""
    conflicts: tuple[str, ...] = ()
    details: tuple[Detail, ...] = ()
    reliability: float | None = None  # learned or starting reliability of its source
    copy_of: str | None = None  # id of the item it repeats, if it is a copy
    denial: str = ""  # the words that call it false, for a contradicting item
    # Who said it, for counting sources: field workers share one display name ("A field
    # worker") but are different sources. Defaults to the display name.
    source_key: str = ""

    @property
    def key(self) -> str:
        return self.source_key or self.source


@dataclass(frozen=True)
class Estimate:
    """The fused value of one detail (from the fusion / assessment step)."""

    attribute: str
    value: object
    unit: str | None
    disputed: bool


@dataclass
class EventFacts:
    id: str
    title: str
    event_type: str
    family: str
    place_name: str | None
    started_at: datetime
    ended_at: datetime | None
    status: str  # active, monitoring, resolved, dismissed
    assessment: str  # the analysts' label
    suggested: str | None = None  # CARCUX's suggested assessment
    probability: float | None = None  # how likely it happened, if known
    estimates: list[Estimate] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)

    def estimate(self, attribute: str) -> Estimate | None:
        return next((e for e in self.estimates if e.attribute == attribute), None)

    def counted(self) -> list[Evidence]:
        """Evidence that counts: not a copy of another item, and about this event."""
        return [e for e in self.evidence if e.copy_of is None and e.relation != "unrelated"]


FIELD_WORKER = "A field worker"
CREDIBLE = 0.5  # as in the assessment (backend assess.CREDIBLE): credible from here up


def label(attribute: str) -> str:
    return {
        "casualty_count": "Deaths",
        "affected_count": "People affected",
        "magnitude": "Severity",
        "cause": "Cause",
        "status": "Status",
        "location": "Place",
    }.get(attribute, attribute.replace("_", " ").capitalize())


def type_label(event_type: str) -> str:
    return event_type.replace("_", " ")
