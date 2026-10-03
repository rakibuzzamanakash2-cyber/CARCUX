"""Public signals: alerts, bulletins and news items collected from outside sources.

A *source* is a feed CARCUX reads (GDACS alerts, a newspaper's RSS feed, ReliefWeb)
or a publisher whose bulletins analysts enter by hand (BMD, FFWC). Each item read
from it becomes a *signal*: a piece of evidence that can be linked to events, like a
field report. Fields follow the CARCUX-BD observation schema (source_type,
content_policy, published_at / collected_at, location precision), so signals can be
exported into the dataset without reshaping.

News text is copyrighted: feeds store a short excerpt (at most 300 characters) and
the link, never the article.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
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

EXCERPT_MAX = 300


def _values(e: type[enum.Enum]) -> list[str]:
    return [m.value for m in e]


class SourceType(enum.StrEnum):
    """Dataset source_type values that apply to collected sources."""

    NEWS = "news"
    PUBLIC_RECORD = "public_record"  # government and UN alerts and bulletins
    OTHER = "other"


class Adapter(enum.StrEnum):
    """How a source is read."""

    GDACS = "gdacs"  # GDACS RSS (geocoded disaster alerts)
    RSS = "rss"  # any RSS or Atom feed; items are filtered and placed by keywords
    RELIEFWEB = "reliefweb"  # ReliefWeb API v2 (needs an approved app name)
    MANUAL = "manual"  # bulletins entered by analysts


class SignalStatus(enum.StrEnum):
    NEW = "new"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"


class Severity(enum.StrEnum):
    MINOR = "minor"
    MODERATE = "moderate"
    SEVERE = "severe"


class ContentPolicy(enum.StrEnum):
    """As in the dataset: how much of the original text is stored."""

    FULL = "full"
    EXCERPT = "excerpt"
    REFERENCE_ONLY = "reference_only"


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(40), unique=True)  # stable slug, e.g. "gdacs"
    name: Mapped[str] = mapped_column(String(120))
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type", values_callable=_values)
    )
    adapter: Mapped[Adapter] = mapped_column(
        Enum(Adapter, name="source_adapter", values_callable=_values)
    )
    url: Mapped[str | None] = mapped_column(String(500))
    domain: Mapped[str | None] = mapped_column(String(120))
    language: Mapped[str] = mapped_column(String(10), default="en")  # dataset language code
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=30)

    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        # Reading a feed twice never duplicates an item.
        UniqueConstraint("source_id", "external_id", name="source_item_once"),
        CheckConstraint(
            "(latitude IS NULL) = (longitude IS NULL)", name="both_coordinates_or_neither"
        ),
        CheckConstraint("latitude IS NULL OR latitude BETWEEN -90 AND 90", name="latitude_valid"),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180", name="longitude_valid"
        ),
        CheckConstraint(
            f"content_policy <> 'excerpt' OR char_length(coalesce(text, '')) <= {EXCERPT_MAX}",
            name="excerpt_is_short",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(300))  # the item's id or link at the source

    title: Mapped[str] = mapped_column(String(400))
    text: Mapped[str | None] = mapped_column(Text)
    content_policy: Mapped[ContentPolicy] = mapped_column(
        Enum(ContentPolicy, name="content_policy", values_callable=_values),
        default=ContentPolicy.EXCERPT,
    )
    url: Mapped[str | None] = mapped_column(String(1000))
    language: Mapped[str] = mapped_column(String(10), default="en")

    event_type: Mapped[str | None] = mapped_column(String(40), index=True)
    family: Mapped[str | None] = mapped_column(String(30))
    severity: Mapped[Severity | None] = mapped_column(
        Enum(Severity, name="signal_severity", values_callable=_values)
    )

    place_name: Mapped[str | None] = mapped_column(String(200))
    district: Mapped[str | None] = mapped_column(String(60))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    precision_m: Mapped[float | None] = mapped_column(Float)

    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Why the item was kept and placed: matched words, place found, source fields.
    extraction: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64))

    status: Mapped[SignalStatus] = mapped_column(
        Enum(SignalStatus, name="signal_status", values_callable=_values),
        default=SignalStatus.NEW,
        index=True,
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    # Set for bulletins entered by hand.
    entered_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    source: Mapped[Source] = relationship(lazy="joined")
    reviewed_by = relationship("User", lazy="joined", foreign_keys=[reviewed_by_id])
    entered_by = relationship("User", lazy="joined", foreign_keys=[entered_by_id])


class IngestRun(Base):
    """One read of one source: what came back, or what went wrong."""

    __tablename__ = "ingest_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    fetched: Mapped[int] = mapped_column(Integer, default=0)  # items in the feed
    created: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)  # not relevant or not placeable
    error: Mapped[str | None] = mapped_column(Text)
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
