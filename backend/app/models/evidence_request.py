"""Requests for more evidence: an analyst asks field workers to go and check an event.

A request carries a question in neutral words ("Is there waterlogging at Mirpur 10 now?
Say what you see, even if nothing is happening"). Field workers see the question, the
place and the kind of event, never the team's assessment or the model's probability,
so that what they report is what they see and not what they were told to expect.

A field report sent in answer to a request records it (field_reports.request_id). The
answers are ordinary reports: an analyst still reviews them and decides how each bears
on the event. At most one request per event is open at a time; an analyst closes it as
answered or cancelled.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RequestStatus(enum.StrEnum):
    OPEN = "open"
    ANSWERED = "answered"
    CANCELLED = "cancelled"


class EvidenceRequest(Base):
    __tablename__ = "evidence_requests"
    __table_args__ = (
        Index(
            "one_open_request_per_event",
            "event_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus, name="evidence_request_status",
             values_callable=lambda e: [m.value for m in e]),
        default=RequestStatus.OPEN,
        index=True,
    )  # fmt: skip
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_note: Mapped[str | None] = mapped_column(String(300))

    event = relationship("Event", lazy="joined")
    created_by = relationship("User", lazy="joined", foreign_keys=[created_by_id])
    closed_by = relationship("User", lazy="joined", foreign_keys=[closed_by_id])
    responses = relationship(
        "FieldReport",
        primaryjoin="FieldReport.request_id == EvidenceRequest.id",
        foreign_keys="FieldReport.request_id",
        order_by="FieldReport.received_at",
        lazy="selectin",
        viewonly=True,
    )
