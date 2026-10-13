import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.event_types import BD_LAT, BD_LON, EVENT_TYPES
from app.models.signal import (
    Adapter,
    ContentPolicy,
    Severity,
    SignalStatus,
    SourceType,
)
from app.schemas.field_report import ReporterRead

LANGUAGES = ("en", "bn", "bn-Latn", "mixed")  # dataset language codes


def _http_url(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not re.match(r"^https?://[^\s/]+", value, re.IGNORECASE):
        raise ValueError("must be an http or https address")
    return value


class SourceBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    name: str
    source_type: SourceType
    adapter: Adapter
    domain: str | None


class SourceRead(SourceBrief):
    url: str | None
    language: str
    enabled: bool
    interval_minutes: int
    last_run_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    signal_count: int = 0
    signals_24h: int = 0


class SourceCreate(BaseModel):
    """A news feed to read (RSS or Atom)."""

    name: str = Field(min_length=2, max_length=120)
    url: str = Field(max_length=500)
    language: str = "en"
    interval_minutes: int = Field(default=30, ge=10, le=1440)

    _url = field_validator("url")(classmethod(lambda cls, v: _http_url(v)))

    @field_validator("language")
    @classmethod
    def _language(cls, value: str) -> str:
        if value not in LANGUAGES:
            raise ValueError(f"must be one of {', '.join(LANGUAGES)}")
        return value

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return value.strip()


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    url: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None
    interval_minutes: int | None = Field(default=None, ge=10, le=1440)

    _url = field_validator("url")(classmethod(lambda cls, v: _http_url(v)))

    @model_validator(mode="after")
    def _no_nulls(self) -> "SourceUpdate":
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be empty")
        return self


class IngestRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None
    ok: bool
    fetched: int
    created: int
    updated: int
    skipped: int
    error: str | None


class SignalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: SourceBrief
    external_id: str
    title: str
    text: str | None
    content_policy: ContentPolicy
    url: str | None
    language: str
    event_type: str | None
    family: str | None
    severity: Severity | None
    place_name: str | None
    district: str | None
    latitude: float | None
    longitude: float | None
    precision_m: float | None
    published_at: datetime
    valid_from: datetime | None
    valid_until: datetime | None
    collected_at: datetime
    updated_at: datetime
    extraction: dict[str, Any]
    status: SignalStatus
    reviewed_by: ReporterRead | None
    reviewed_at: datetime | None
    review_note: str | None
    entered_by: ReporterRead | None


class SignalPage(BaseModel):
    items: list[SignalRead]
    total: int
    limit: int
    offset: int


class SignalCreate(BaseModel):
    """A bulletin entered by hand (BMD, FFWC and other publishers without a feed).

    Place it by district (its centre stands for the district), or by coordinates."""

    source_id: uuid.UUID
    title: str = Field(min_length=5, max_length=400)
    text: str | None = Field(default=None, max_length=4000)
    url: str | None = Field(default=None, max_length=1000)
    event_type: str
    severity: Severity | None = None
    published_at: datetime
    valid_until: datetime | None = None
    district: str | None = None
    place_name: str | None = Field(default=None, max_length=200)
    latitude: float | None = Field(default=None, ge=BD_LAT[0], le=BD_LAT[1])
    longitude: float | None = Field(default=None, ge=BD_LON[0], le=BD_LON[1])
    language: str = "en"

    _url = field_validator("url")(classmethod(lambda cls, v: _http_url(v)))

    @field_validator("title", "text", "place_name", "district", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("event_type")
    @classmethod
    def _event_type(cls, value: str) -> str:
        if value not in EVENT_TYPES:
            raise ValueError(f"Unknown event_type '{value}'")
        return value

    @field_validator("published_at", "valid_until")
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("must include a UTC offset, e.g. +06:00")
        return value

    @field_validator("language")
    @classmethod
    def _language(cls, value: str) -> str:
        if value not in LANGUAGES:
            raise ValueError(f"must be one of {', '.join(LANGUAGES)}")
        return value

    @model_validator(mode="after")
    def _placed_once(self) -> "SignalCreate":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Give both latitude and longitude, or neither")
        if self.district is None and self.latitude is None:
            raise ValueError("Say where: a district, or coordinates")
        if self.valid_until is not None and self.valid_until < self.published_at:
            raise ValueError("valid_until must not be before published_at")
        return self


class SignalReview(BaseModel):
    status: SignalStatus
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("note", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def _reason_to_dismiss(self) -> "SignalReview":
        if self.status == SignalStatus.DISMISSED and not self.note:
            raise ValueError("Say why the signal is dismissed")
        return self


class District(BaseModel):
    name: str
    division: str
    latitude: float
    longitude: float
