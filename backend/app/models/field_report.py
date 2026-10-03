"""Field reports: what an authorised field worker saw, where and when.

Each report stores a SHA-256 `content_hash` over its content and photos, computed
at submission. Recomputing it later (see services/field_reports.verify) shows
whether anything was changed afterwards: tamper-evident, not tamper-proof.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ReportStatus(enum.StrEnum):
    SUBMITTED = "submitted"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"


class FieldReport(Base):
    __tablename__ = "field_reports"
    __table_args__ = (
        # Offline phones retry; the same client id from the same reporter is one report.
        UniqueConstraint("reporter_id", "client_report_id", name="reporter_client_id"),
        CheckConstraint("latitude BETWEEN 20.5 AND 26.7", name="latitude_in_bangladesh"),
        CheckConstraint("longitude BETWEEN 88.0 AND 92.7", name="longitude_in_bangladesh"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    client_report_id: Mapped[uuid.UUID]
    reporter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)

    text: Mapped[str] = mapped_column(Text)
    event_type: Mapped[str | None] = mapped_column(String(40))
    place_name: Mapped[str | None] = mapped_column(String(200))

    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    location_accuracy_m: Mapped[float | None] = mapped_column(Float)

    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    status: Mapped[ReportStatus] = mapped_column(
        Enum(
            ReportStatus,
            name="report_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=ReportStatus.SUBMITTED,
    )
    content_hash: Mapped[str] = mapped_column(String(64))
    hash_version: Mapped[int] = mapped_column(Integer, default=1)
    integrity_flags: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)

    # Triage by an analyst: who last set the status, when, and why (required to dismiss).
    # Not part of the content hash: reviewing a report does not change what was reported.
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)

    media: Mapped[list["FieldReportMedia"]] = relationship(
        back_populates="report", order_by="FieldReportMedia.position", lazy="selectin"
    )
    reporter = relationship("User", lazy="joined", foreign_keys=[reporter_id])
    reviewed_by = relationship("User", lazy="joined", foreign_keys=[reviewed_by_id])


class FieldReportMedia(Base):
    __tablename__ = "field_report_media"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("field_reports.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(40))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    # 64-bit difference hash (hex): near-identical images have close hashes.
    dhash: Mapped[str] = mapped_column(String(16))
    # Relative path under the media directory. Never derived from user input.
    storage_key: Mapped[str] = mapped_column(String(200))

    report: Mapped[FieldReport] = relationship(back_populates="media")
