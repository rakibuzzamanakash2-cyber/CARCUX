import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.event import ClaimAttribute, EvidenceRelation
from app.models.signal import ContentPolicy, Severity
from app.schemas.event import EventRead, GroundTruthSource
from app.schemas.field_report import FieldReportRead, IntegrityFlag, MediaRead, ReporterRead
from app.schemas.signal import SignalRead, SourceBrief


def _strip(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


# The queue is blind: it carries what an annotator needs to judge the item against the
# event and nothing that reveals another judgement: no labels or evidence counts, no
# assessment, no CARCUX extraction or stance, no reviewer and no names of other staff.


class BlindEvent(BaseModel):
    """The event as it is judged against: what, where, when, and its ground truth."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    summary: str | None
    event_type: str
    family: str
    place_name: str | None
    latitude: float
    longitude: float
    started_at: datetime
    ended_at: datetime | None
    occurred: bool | None
    ground_truth_sources: list[GroundTruthSource]
    ground_truth_note: str | None


class BlindSignal(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: SourceBrief
    title: str
    text: str | None
    content_policy: ContentPolicy
    url: str | None
    language: str
    event_type: str | None
    severity: Severity | None
    place_name: str | None
    precision_m: float | None
    published_at: datetime


class BlindFieldReport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    text: str
    event_type: str | None
    place_name: str | None
    latitude: float
    longitude: float
    observed_at: datetime
    media: list[MediaRead]
    integrity_flags: list[IntegrityFlag]


class QueueItem(BaseModel):
    """A link to judge, without anyone's label (the second opinion is blind)."""

    evidence_id: uuid.UUID
    event: BlindEvent
    field_report: BlindFieldReport | None
    signal: BlindSignal | None
    judgements: int


class QueuePage(BaseModel):
    items: list[QueueItem]
    total: int


class JudgementCreate(BaseModel):
    evidence_id: uuid.UUID
    relation: EvidenceRelation
    conflicts: list[ClaimAttribute] = Field(default_factory=list)
    stale: bool = False
    confidence: int = Field(2, ge=1, le=3)
    note: str | None = Field(default=None, max_length=2000)

    _note = field_validator("note", mode="before")(classmethod(lambda cls, v: _strip(v)))

    @field_validator("conflicts")
    @classmethod
    def _unique(cls, value: list[ClaimAttribute]) -> list[ClaimAttribute]:
        return list(dict.fromkeys(value))


class JudgementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    annotator: ReporterRead
    relation: EvidenceRelation
    conflicts: list[ClaimAttribute]
    stale: bool
    confidence: int
    note: str | None
    blind: bool
    created_at: datetime
    updated_at: datetime


class Adjudication(BaseModel):
    evidence_id: uuid.UUID
    relation: EvidenceRelation
    conflicts: list[ClaimAttribute] = Field(default_factory=list)
    note: str | None = Field(default=None, max_length=2000)

    _note = field_validator("note", mode="before")(classmethod(lambda cls, v: _strip(v)))


class Disagreement(BaseModel):
    evidence_id: uuid.UUID
    event: EventRead
    field_report: FieldReportRead | None
    signal: SignalRead | None
    working: EvidenceRelation
    judgements: list[JudgementRead]
    gold_relation: EvidenceRelation | None
    gold_by: ReporterRead | None
    gold_at: datetime | None


class AgreementRead(BaseModel):
    items_with_two: int
    items_total: int
    percent: float | None
    kappa: float | None
    alpha: float | None
    target: float
    matrix: dict[str, dict[str, int]]
    by_label: dict[str, int]
    open_disagreements: int
