import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.extraction import extract
from app.models.field_report import ReportStatus


class DetailRead(BaseModel):
    """A detail the text states, found automatically (app/extraction): what, the value,
    and the words it came from. A machine reading: analysts check it."""

    attribute: str = Field(
        description="occurrence (false = denied), casualty_count (deaths), affected_count, "
        "magnitude, cause or status"
    )
    value: bool | int | float | str
    unit: str | None = None
    surface: str = Field(description="The words it was read from")


def details_of(text: str) -> list[DetailRead]:
    return [DetailRead(**c.as_dict()) for c in extract(text)]


class IntegrityFlag(BaseModel):
    code: str
    detail: str


class MediaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    content_type: str
    size_bytes: int
    width: int
    height: int
    sha256: str
    # Text read in the photo after submission; status None while waiting.
    ocr_text: str | None = None
    ocr_confidence: float | None = None
    ocr_status: str | None = None


class ReporterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str


class FieldReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_report_id: uuid.UUID
    reporter: ReporterRead
    text: str
    event_type: str | None
    place_name: str | None
    latitude: float
    longitude: float
    location_accuracy_m: float | None
    observed_at: datetime
    received_at: datetime
    status: ReportStatus
    content_hash: str
    integrity_flags: list[IntegrityFlag]
    media: list[MediaRead]
    reviewed_by: ReporterRead | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None

    @computed_field
    @property
    def details(self) -> list[DetailRead]:
        """Details the text states, found automatically."""
        return details_of(self.text)


class FieldReportPage(BaseModel):
    items: list[FieldReportRead]
    total: int
    limit: int
    offset: int


class VerifyResult(BaseModel):
    report_id: uuid.UUID
    intact: bool
    problems: list[str]
    content_hash: str


class ReviewDecision(BaseModel):
    """Triage a report: reviewed (looked at), dismissed (not usable; say why) or back to new."""

    status: ReportStatus
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _dismissal_needs_reason(self) -> "ReviewDecision":
        if self.note is not None:
            self.note = self.note.strip() or None
        if self.status == ReportStatus.DISMISSED and not self.note:
            raise ValueError("Say why the report is dismissed")
        return self
