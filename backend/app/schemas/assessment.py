import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.event import Assessment
from app.schemas.field_report import ReporterRead


class AssessmentReason(BaseModel):
    """One source behind a suggestion: what it says and how much it is trusted."""

    source: str
    kind: str = Field(description="field, news, public_record or other")
    vote: Literal[1, -1] = Field(description="1 says it happened, -1 says it did not")
    reliability: float = Field(ge=0, le=1)
    learned: bool = Field(description="From this source's own record (else its kind's)")
    disputed: list[str] = Field(description="Details this source has wrong (partly supports)")


class AssessmentSuggestionRead(BaseModel):
    """The suggested assessment for an event, and why.

    `method` is "start" (starting assumptions about each kind of source) until an
    admin trains a model on events with ground truth, then "model"."""

    label: Assessment
    probability: float | None = Field(
        description="That the event really happened; None without evidence"
    )
    method: Literal["start", "model"]
    model_id: uuid.UUID | None
    sources_supporting: int
    sources_denying: int
    credible_supporting: int
    credible_denying: int
    disputed: list[str]
    reasons: list[AssessmentReason]


class AssessmentModelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    created_by: ReporterRead | None
    active: bool
    events: int
    happened: int
    sources: int
    metrics: dict[str, Any]


class AssessmentStatus(BaseModel):
    """What assessment suggestions run on now, and whether a model can be trained."""

    method: Literal["start", "model"]
    active: AssessmentModelRead | None
    resolved_events: int = Field(description="Events with ground truth and linked evidence")
    resolved_happened: int
    min_events: int
    min_each: int
    starting_rates: dict[str, float]
    from_suggestions: dict[str, int] = Field(
        description="Assessments set with a suggestion in view: total, followed"
    )
