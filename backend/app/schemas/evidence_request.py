import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.event import Assessment, EventStatus, Priority
from app.models.evidence_request import RequestStatus
from app.schemas.field_report import ReporterRead


class EvidenceRequestCreate(BaseModel):
    question: str = Field(
        min_length=10,
        max_length=500,
        description="What to check, in neutral words. Field workers see this, the place and "
        "the kind of event, never the assessment.",
    )


class EvidenceRequestClose(BaseModel):
    status: Literal["answered", "cancelled"]
    note: str | None = Field(default=None, max_length=300)


class ResponseRead(BaseModel):
    """A report sent in answer, as analysts see it (the report itself is reviewed as usual)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reporter: ReporterRead
    text: str
    observed_at: datetime
    received_at: datetime
    latitude: float
    longitude: float


class EvidenceRequestRead(BaseModel):
    """A request as analysts see it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    question: str
    status: RequestStatus
    created_by: ReporterRead
    created_at: datetime
    closed_by: ReporterRead | None = None
    closed_at: datetime | None = None
    close_note: str | None = None
    responses: list[ResponseRead]


class RequestForWorkers(BaseModel):
    """An open request as field workers see it: what to check and where, nothing about
    what the team or the model currently believes."""

    id: uuid.UUID
    question: str
    event_type: str
    place_name: str | None
    latitude: float
    longitude: float
    created_at: datetime
    answered_by_me: int = Field(description="Reports you have already sent in answer")


class CheckValueRead(BaseModel):
    probability: float | None = Field(description="Now; null without evidence")
    if_supported: float = Field(description="After one more field report saying it is happening")
    if_denied: float = Field(description="After one more field report saying it is not")
    chance_supported: float
    changes: float = Field(description="Chance that one more report changes the assessment")
    uncertainty: float


class QueueEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    event_type: str
    place_name: str | None
    status: EventStatus
    priority: Priority
    assessment: Assessment
    started_at: datetime


class OpenRequestBrief(BaseModel):
    id: uuid.UUID
    question: str
    created_at: datetime
    responses: int


class QueueItemRead(BaseModel):
    event: QueueEvent
    suggested: Assessment
    differs: bool = Field(description="The team's assessment differs from the suggested one")
    value: CheckValueRead
    impact: int
    need: float
    score: float
    reasons: list[str]
    open_request: OpenRequestBrief | None
    last_evidence_at: datetime | None


class QueuePage(BaseModel):
    items: list[QueueItemRead]
    total: int = Field(description="Open (active or monitoring) events")
