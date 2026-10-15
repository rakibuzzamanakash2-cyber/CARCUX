"""Analysts' decisions on copies: is an item about an event a copy of an earlier item
from another source (a repost, a rewrite, the same photo, "according to …")?

Copies are detected automatically (services/copies.py) and shown on the event's
evidence. An analyst can confirm one (or name the origin themselves) or say it is not
a copy; the decision overrides the detection. One decision per linked item.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CopyDecision(Base):
    __tablename__ = "copy_decisions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # The linked item that is (or is not) a copy.
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("event_evidence.id", ondelete="CASCADE"), unique=True
    )
    # What it copies; None means "not a copy".
    origin_evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("event_evidence.id", ondelete="CASCADE")
    )
    decided_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    decided_by = relationship("User", lazy="joined")
