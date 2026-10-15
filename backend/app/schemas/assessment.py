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


class StatedValue(BaseModel):
    """One source's value for a detail, read from its text."""

    value: bool | int | float | str
    unit: str | None
    source: str
    reliability: float = Field(ge=0, le=1)
    surface: str = Field(description="The words it was read from")


class DetailSummaryRead(BaseModel):
    """What the supporting sources state about one detail."""

    attribute: str = Field(description="magnitude, affected_count, casualty_count or cause")
    estimate: bool | int | float | str = Field(
        description="Weighted by reliability: median for counts, most supported otherwise"
    )
    unit: str | None
    disputed: bool = Field(description="Two credible sources state values that disagree")
    statements: list[StatedValue]


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
    disputed: list[str] = Field(
        description="Details in dispute: marked by analysts or detected from the texts"
    )
    disputed_detected: list[str] = Field(
        description="Of those, detected: credible sources state values that disagree"
    )
    reasons: list[AssessmentReason]
    details: list[DetailSummaryRead]
    counted_once: int = Field(
        0, description="Linked items that copy another source's and are not counted again"
    )


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
