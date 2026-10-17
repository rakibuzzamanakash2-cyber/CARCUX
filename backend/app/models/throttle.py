import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ThrottleEvent(Base):
    """One counted attempt (a failed sign-in, a sign-up, a submission), for rate limits.

    `key` is a keyed hash of the email or account, never the email itself; rows older
    than a day are deleted as new ones arrive (app/services/throttle.py)."""

    __tablename__ = "throttle_events"
    __table_args__ = (Index("ix_throttle_events_kind_at", "kind", "at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(32))
    key: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(45))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
