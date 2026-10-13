import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.event_types import BD_LAT, BD_LON, EVENT_TYPES
from app.models.event import (
    Assessment,
    ClaimAttribute,
    EventStatus,
    EvidenceRelation,
    GroundTruthKind,
    Priority,
)
from app.schemas.field_report import FieldReportRead, ReporterRead
from app.schemas.signal import SignalRead


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


class GroundTruthSource(BaseModel):
    """A source published after the event that says what really happened."""

    reference: str = Field(max_length=1000)
    published_at: datetime
    kind: GroundTruthKind

    @field_validator("reference")
    @classmethod
    def _url(cls, value: str) -> str:
        value = value.strip()
        if not value.lower().startswith(("http://", "https://")) or " " in value:
            raise ValueError("must be an http or https address")
        return value

    @field_validator("published_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        return _check_aware(value)


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
    signal_ids: list[uuid.UUID] = Field(
        default_factory=list,
        max_length=50,
        description="Signals to attach as supporting evidence when the event is created",
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
    occurred: bool | None = Field(
        default=None, description="Ground truth: did it happen? null = not established yet"
    )
    ground_truth_sources: list[GroundTruthSource] | None = Field(default=None, max_length=20)
    ground_truth_note: str | None = Field(default=None, max_length=2000)

    @field_validator("ground_truth_note", mode="before")
    @classmethod
    def _note(cls, value: Any) -> Any:
        return _strip(value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def _no_null_required(self) -> "EventUpdate":
        clearable = {"summary", "place_name", "ended_at", "occurred", "ground_truth_note"}
        for name in self.model_fields_set - clearable:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be empty")
        return self

    def changes(self) -> dict[str, Any]:
        changes = self.model_dump(exclude_unset=True)
        if "ground_truth_sources" in changes:  # stored as JSON
            changes["ground_truth_sources"] = [
                s.model_dump(mode="json") for s in self.ground_truth_sources or []
            ]
        return changes


class EvidenceCounts(BaseModel):
    supports: int = 0
    partially_supports: int = 0
    contradicts: int = 0
    related: int = 0
    reporters: int = Field(0, description="Distinct field workers among the evidence")
    photos: int = 0
    signals: int = Field(0, description="Public signals among the evidence")


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
    occurred: bool | None
    ground_truth_sources: list[GroundTruthSource]
    ground_truth_note: str | None


class EventPage(BaseModel):
    items: list[EventRead]
    total: int
    limit: int
    offset: int


class _EvidenceLabels(_NoteCheck):
    """Dataset fields of a link, checked the way the dataset checks them."""

    @field_validator("conflicts", check_fields=False)
    @classmethod
    def _unique(cls, value: list[ClaimAttribute] | None) -> list[ClaimAttribute] | None:
        return list(dict.fromkeys(value)) if value is not None else None


class EvidenceCreate(_EvidenceLabels):
    """Link a field report or a signal (exactly one)."""

    field_report_id: uuid.UUID | None = None
    signal_id: uuid.UUID | None = None
    relation: EvidenceRelation
    note: str | None = Field(default=None, max_length=2000)
    conflicts: list[ClaimAttribute] = Field(
        default_factory=list,
        description="What the item gets wrong; required for partially_supports",
    )
    stale: bool = Field(False, description="Already out of date when published")
    confidence: int = Field(2, ge=1, le=3, description="1 unsure, 2 fairly sure, 3 certain")

    @model_validator(mode="after")
    def _exactly_one(self) -> "EvidenceCreate":
        if (self.field_report_id is None) == (self.signal_id is None):
            raise ValueError("Give either field_report_id or signal_id")
        check_conflicts(self.relation, self.conflicts)
        return self


def check_conflicts(relation: EvidenceRelation, conflicts: list) -> None:
    if relation == EvidenceRelation.PARTIALLY_SUPPORTS and not conflicts:
        raise ValueError("Say what it gets wrong: partly supports needs at least one conflict")
    if relation == EvidenceRelation.RELATED and conflicts:
        raise ValueError("A related-only item makes no checkable claim, so it has no conflicts")


class EvidenceUpdate(_EvidenceLabels):
    relation: EvidenceRelation | None = None
    note: str | None = Field(default=None, max_length=2000)
    conflicts: list[ClaimAttribute] | None = None
    stale: bool | None = None
    confidence: int | None = Field(default=None, ge=1, le=3)

    @model_validator(mode="after")
    def _relation_not_null(self) -> "EvidenceUpdate":
        for name in ("relation", "conflicts", "stale", "confidence"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be empty")
        return self


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    relation: EvidenceRelation
    note: str | None
    linked_by: ReporterRead
    linked_at: datetime
    conflicts: list[ClaimAttribute]
    stale: bool
    confidence: int
    field_report: FieldReportRead | None
    signal: SignalRead | None


class CandidateReport(BaseModel):
    """A report that may belong to an event: close in space and time, not yet linked."""

    report: FieldReportRead
    distance_km: float
    hours_apart: float
    same_type: bool


class CandidateSignal(BaseModel):
    """A signal that may be about an event."""

    signal: SignalRead
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
