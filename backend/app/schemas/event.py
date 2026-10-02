import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.event_types import BD_LAT, BD_LON, EVENT_TYPES
from app.models.event import Assessment, EventStatus, EvidenceRelation, Priority
from app.schemas.field_report import FieldReportRead, ReporterRead


def _check_event_type(value: str | None) -> str | None:
    if value is not None and value not in EVENT_TYPES:
        raise ValueError(f"Unknown event_type '{value}'")
    return value


def _check_aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        raise ValueError("must include a UTC offset, e.g. +06:00")
    return value


def _strip(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class _EventChecks(BaseModel):
    """Validators shared by create and update."""

    @field_validator("event_type", check_fields=False)
    @classmethod
    def _event_type(cls, value: str | None) -> str | None:
        return _check_event_type(value)

    @field_validator("started_at", "ended_at", check_fields=False)
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        return _check_aware(value)

    @field_validator("summary", "place_name", mode="before", check_fields=False)
    @classmethod
    def _optional_text(cls, value: Any) -> Any:
        return _strip(value) if isinstance(value, str) else value

    @field_validator("title", check_fields=False)
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if len(value) < 5:
            raise ValueError("title must be at least 5 characters")
        return value


class _NoteCheck(BaseModel):
    @field_validator("note", mode="before", check_fields=False)
    @classmethod
    def _note(cls, value: Any) -> Any:
        return _strip(value) if isinstance(value, str) else value


class EventCreate(_EventChecks):
    title: str = Field(min_length=5, max_length=160)
    event_type: str
    summary: str | None = Field(default=None, max_length=4000)
    place_name: str | None = Field(default=None, max_length=200)
    latitude: float = Field(ge=BD_LAT[0], le=BD_LAT[1])
    longitude: float = Field(ge=BD_LON[0], le=BD_LON[1])
    started_at: datetime
    ended_at: datetime | None = None
    status: EventStatus = EventStatus.ACTIVE
    priority: Priority = Priority.MEDIUM
    assessment: Assessment = Assessment.UNVERIFIED
    field_report_ids: list[uuid.UUID] = Field(
        default_factory=list,
        max_length=50,
        description="Reports to attach as supporting evidence when the event is created",
    )

    @model_validator(mode="after")
    def _ends_after_start(self) -> "EventCreate":
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("ended_at must not be before started_at")
        return self


class EventUpdate(_EventChecks):
    """Only the fields sent are changed. Send null to clear summary, place_name or ended_at."""

    title: str | None = Field(default=None, min_length=5, max_length=160)
    event_type: str | None = None
    summary: str | None = Field(default=None, max_length=4000)
    place_name: str | None = Field(default=None, max_length=200)
    latitude: float | None = Field(default=None, ge=BD_LAT[0], le=BD_LAT[1])
    longitude: float | None = Field(default=None, ge=BD_LON[0], le=BD_LON[1])
    started_at: datetime | None = None
    ended_at: datetime | None = None
    status: EventStatus | None = None
    priority: Priority | None = None
    assessment: Assessment | None = None

    @model_validator(mode="after")
    def _no_null_required(self) -> "EventUpdate":
        clearable = {"summary", "place_name", "ended_at"}
        for name in self.model_fields_set - clearable:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be empty")
        return self

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class EvidenceCounts(BaseModel):
    supports: int = 0
    partially_supports: int = 0
    contradicts: int = 0
    related: int = 0
    reporters: int = Field(0, description="Distinct field workers among the evidence")
    photos: int = 0


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    summary: str | None
    event_type: str
    family: str
    status: EventStatus
    priority: Priority
    assessment: Assessment
    place_name: str | None
    latitude: float
    longitude: float
    started_at: datetime
    ended_at: datetime | None
    created_by: ReporterRead
    created_at: datetime
    updated_at: datetime
    evidence_counts: EvidenceCounts


class EventPage(BaseModel):
    items: list[EventRead]
    total: int
    limit: int
    offset: int


class EvidenceCreate(_NoteCheck):
    field_report_id: uuid.UUID
    relation: EvidenceRelation
    note: str | None = Field(default=None, max_length=2000)


class EvidenceUpdate(_NoteCheck):
    relation: EvidenceRelation | None = None
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _relation_not_null(self) -> "EvidenceUpdate":
        if "relation" in self.model_fields_set and self.relation is None:
            raise ValueError("relation cannot be empty")
        return self


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    relation: EvidenceRelation
    note: str | None
    linked_by: ReporterRead
    linked_at: datetime
    field_report: FieldReportRead


class CandidateReport(BaseModel):
    """A report that may belong to an event: close in space and time, not yet linked."""

    report: FieldReportRead
    distance_km: float
    hours_apart: float
    same_type: bool


class CandidateEvent(BaseModel):
    """An event a report may belong to."""

    event: EventRead
    distance_km: float
    hours_apart: float
    same_type: bool
    same_family: bool


class ReportLink(BaseModel):
    """An event a report is linked to, and how."""

    evidence_id: uuid.UUID
    relation: EvidenceRelation
    event: EventRead


class HistoryEntry(BaseModel):
    occurred_at: datetime
    action: str
    actor: ReporterRead | None
    details: dict[str, Any]
