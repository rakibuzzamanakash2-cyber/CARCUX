import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.field_report import ReportStatus


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
