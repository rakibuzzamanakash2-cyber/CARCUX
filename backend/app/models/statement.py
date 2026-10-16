"""Official statements: what a verified official page says about an event.

An official writes the statement in their own words with CARCUX's brief beside them.
The brief at that moment is kept with the statement, and every statement written here
is marked as informed by CARCUX: it can never serve as ground truth for evaluating
CARCUX, which would be CARCUX grading itself.

Statements are never edited. A correction is a new statement that supersedes the old
one; both stay readable.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Finding(enum.StrEnum):
    """What the statement says about whether the event happened as reported."""

    CONFIRMED = "confirmed"
    PARTLY_CONFIRMED = "partly_confirmed"  # it happened, but not as reported
    DENIED = "denied"  # it did not happen
    UNDER_REVIEW = "under_review"  # being checked; no finding yet


class Statement(Base):
    __tablename__ = "statements"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    page_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("official_pages.id"), index=True)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    finding: Mapped[Finding] = mapped_column(
        Enum(Finding, name="statement_finding", values_callable=lambda e: [m.value for m in e])
    )
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    # The statement this one corrects; at most one correction per statement.
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("statements.id"), unique=True
    )
    informed_by_carcux: Mapped[bool] = mapped_column(Boolean, server_default="true")
    # CARCUX's brief as the official saw it when publishing.
    brief: Mapped[dict[str, Any]] = mapped_column(JSONB)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    page = relationship("OfficialPage", lazy="joined")
    author = relationship("User", lazy="joined")
    event = relationship("Event")
    supersedes = relationship("Statement", remote_side=[id], foreign_keys=[supersedes_id])
