import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.event import ClaimAttribute, EvidenceRelation
from app.schemas.event import EventRead
from app.schemas.field_report import FieldReportRead, ReporterRead
from app.schemas.signal import SignalRead


def _strip(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


class QueueItem(BaseModel):
    """A link to judge, without anyone's label (the second opinion is blind)."""

    evidence_id: uuid.UUID
    event: EventRead
    field_report: FieldReportRead | None
    signal: SignalRead | None
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
