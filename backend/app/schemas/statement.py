import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.official import PageKind, PageStatus
from app.models.statement import Finding


class StatementCreate(BaseModel):
    event_id: uuid.UUID
    finding: Finding
    title: str = Field(min_length=5, max_length=200)
    body: str = Field(min_length=20, max_length=5000)
    supersedes_id: uuid.UUID | None = Field(
        default=None, description="The statement this one corrects"
    )


class PageLite(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    name_bn: str | None
    kind: PageKind
    status: PageStatus


class EventLite(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    event_type: str
    place_name: str | None
    started_at: datetime


class StatementRead(BaseModel):
    id: uuid.UUID
    page: PageLite
    event: EventLite
    finding: Finding
    title: str
    body: str
    published_at: datetime
    informed_by_carcux: bool
    supersedes_id: uuid.UUID | None
    superseded_by_id: uuid.UUID | None
    author: str | None = Field(
        None, description="The official who wrote it; for admins and the page's officials"
    )


class StatementDetail(StatementRead):
    brief: dict[str, Any] = Field(description="CARCUX's brief as the official saw it")
