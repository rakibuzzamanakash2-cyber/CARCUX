from datetime import datetime

from pydantic import BaseModel


class PriorityFactor(BaseModel):
    name: str  # hazard, deaths, affected, severity, disruption, growing, rising, duration …
    points: int
    reason: str


class PrioritySuggestionRead(BaseModel):
    level: str  # low, medium, high, critical
    score: int
    factors: list[PriorityFactor]


class CitedSentence(BaseModel):
    text: str
    cites: list[str]  # ids of the event's evidence links
    kind: str


class BriefingRead(BaseModel):
    """Decision support for one event. Suggestions only: the analyst decides."""

    generated_at: datetime
    since: datetime
    priority: PrioritySuggestionRead
    summary: list[CitedSentence]
    changes: list[CitedSentence]
