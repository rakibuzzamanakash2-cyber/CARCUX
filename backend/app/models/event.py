"""Events and the evidence attached to them.

An event is the analyst's working record of one real-world situation ("waterlogging
at Mirpur 10, 3 Oct"). Evidence links field reports and public signals to it, each with a relation:
does the report support the event, only partly, contradict it, or merely relate to
it? The vocabulary matches the CARCUX-BD dataset (relation.schema.json,
common.schema.json), so what analysts record here can be compared with the gold
annotations and, later, with the fusion engine's own assessment.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _values(e: type[enum.Enum]) -> list[str]:
    return [m.value for m in e]


class EventStatus(enum.StrEnum):
    ACTIVE = "active"  # happening now, needs attention
    MONITORING = "monitoring"  # easing, still watched
    RESOLVED = "resolved"  # over
    DISMISSED = "dismissed"  # not a real event (duplicate, mistaken, refuted)


class Priority(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Assessment(enum.StrEnum):
    """Same labels and meaning as the dataset's assessment_label."""

    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    CONFLICTING = "conflicting"
    UNVERIFIED = "unverified"
    REFUTED = "refuted"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class EvidenceRelation(enum.StrEnum):
    """How a piece of evidence bears on the event (dataset relation labels)."""

    SUPPORTS = "supports"
    PARTIALLY_SUPPORTS = "partially_supports"
    CONTRADICTS = "contradicts"
    RELATED = "related"
    # About a different event (wrong place, day or type): a hard negative for the model.
    UNRELATED = "unrelated"


# Relations that are evidence about the event (unrelated items are kept as negatives).
ABOUT_THE_EVENT = frozenset(
    {
        EvidenceRelation.SUPPORTS,
        EvidenceRelation.PARTIALLY_SUPPORTS,
        EvidenceRelation.CONTRADICTS,
        EvidenceRelation.RELATED,
    }
)


class ClaimAttribute(enum.StrEnum):
    """What a claim is about (dataset claim_attribute). Conflicts are recorded per attribute."""

    OCCURRENCE = "occurrence"
    EVENT_TYPE = "event_type"
    LOCATION = "location"
    START_TIME = "start_time"
    END_TIME = "end_time"
    STATUS = "status"
    MAGNITUDE = "magnitude"
    AFFECTED_COUNT = "affected_count"
    CASUALTY_COUNT = "casualty_count"
    CAUSE = "cause"


class GroundTruthKind(enum.StrEnum):
    """Kinds of post-event source (dataset ground_truth.sources[].kind)."""

    OFFICIAL = "official"
    NEWS_FOLLOWUP = "news_followup"
    HUMANITARIAN_REPORT = "humanitarian_report"
    OTHER = "other"


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("latitude BETWEEN 20.5 AND 26.7", name="latitude_in_bangladesh"),
        CheckConstraint("longitude BETWEEN 88.0 AND 92.7", name="longitude_in_bangladesh"),
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="ends_after_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    family: Mapped[str] = mapped_column(String(30), index=True)

    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus, name="event_status", values_callable=_values),
        default=EventStatus.ACTIVE,
        index=True,
    )
    priority: Mapped[Priority] = mapped_column(
        Enum(Priority, name="event_priority", values_callable=_values), default=Priority.MEDIUM
    )
    assessment: Mapped[Assessment] = mapped_column(
        Enum(Assessment, name="assessment_label", values_callable=_values),
        default=Assessment.UNVERIFIED,
    )

    place_name: Mapped[str | None] = mapped_column(String(200))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Ground truth, established afterwards from post-event sources (dataset ground_truth).
    # occurred is None until someone has checked. Sources: [{reference, published_at, kind}].
    occurred: Mapped[bool | None] = mapped_column(Boolean)
    ground_truth_sources: Mapped[list[dict]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    ground_truth_note: Mapped[str | None] = mapped_column(Text)

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    created_by = relationship("User", lazy="joined")
    evidence: Mapped[list["EventEvidence"]] = relationship(
        back_populates="event", order_by="EventEvidence.linked_at", lazy="selectin"
    )

    @property
    def evidence_counts(self) -> dict[str, int]:
        """Tally of the evidence by relation, plus distinct reporters and photos."""
        counts = {r.value: 0 for r in EvidenceRelation}
        reporters: set[uuid.UUID] = set()
        photos = signals = 0
        for item in self.evidence:
            counts[item.relation.value] += 1
            if item.relation not in ABOUT_THE_EVENT:
                continue
            if item.field_report is not None:
                reporters.add(item.field_report.reporter_id)
                photos += len(item.field_report.media)
            else:
                signals += 1
        return {**counts, "reporters": len(reporters), "photos": photos, "signals": signals}


class EventEvidence(Base):
    __tablename__ = "event_evidence"
    __table_args__ = (
        # A report or signal is linked to an event at most once; change the relation instead.
        UniqueConstraint("event_id", "field_report_id", name="event_report_once"),
        UniqueConstraint("event_id", "signal_id", name="event_signal_once"),
        CheckConstraint(
            "num_nonnulls(field_report_id, signal_id) = 1", name="one_kind_of_evidence"
        ),
        CheckConstraint("confidence BETWEEN 1 AND 3", name="confidence_1_to_3"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"), index=True)
    # Exactly one of: a field report, or a public signal (alert, bulletin, news item).
    field_report_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("field_reports.id"), index=True
    )
    signal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("signals.id"), index=True)
    relation: Mapped[EvidenceRelation] = mapped_column(
        Enum(EvidenceRelation, name="evidence_relation", values_callable=_values)
    )
    note: Mapped[str | None] = mapped_column(Text)
    # Dataset fields: attributes the item gets wrong (required for partially_supports),
    # whether it was already out of date when published, and how sure the analyst is
    # (1 unsure, 2 fairly sure, 3 certain).
    conflicts: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    stale: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    confidence: Mapped[int] = mapped_column(SmallInteger, default=2, server_default="2")
    linked_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Adjudicated (gold) judgement, once annotators' disagreement has been resolved.
    gold_relation: Mapped[EvidenceRelation | None] = mapped_column(
        Enum(
            EvidenceRelation, name="evidence_relation", values_callable=_values, create_type=False
        )  # fmt: skip
    )
    gold_conflicts: Mapped[list[str] | None] = mapped_column(JSONB)
    gold_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    gold_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    event: Mapped[Event] = relationship(back_populates="evidence")
    field_report = relationship("FieldReport", lazy="joined")
    signal = relationship("Signal", lazy="joined")
    linked_by = relationship("User", lazy="joined", foreign_keys=[linked_by_id])
    gold_by = relationship("User", lazy="joined", foreign_keys=[gold_by_id])
    judgements: Mapped[list["EvidenceJudgement"]] = relationship(
        back_populates="evidence",
        order_by="EvidenceJudgement.created_at",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    @property
    def judgement_count(self) -> int:
        return len(self.judgements)

    @property
    def agreement(self) -> str:
        """single (one annotator), agree, disagree, or resolved (gold label set)."""
        if self.gold_relation is not None:
            return "resolved"
        if len(self.judgements) < 2:
            return "single"
        labels = {(j.relation, tuple(sorted(j.conflicts or []))) for j in self.judgements}
        return "agree" if len(labels) == 1 else "disagree"


class EvidenceJudgement(Base):
    """One annotator's own judgement of one link, made independently (guideline 7).

    The link's relation is the working label; judgements are what agreement is measured
    on and what the dataset exports as annotations."""

    __tablename__ = "evidence_judgements"
    __table_args__ = (
        UniqueConstraint("evidence_id", "annotator_id", name="one_judgement_each"),
        CheckConstraint("confidence BETWEEN 1 AND 3", name="confidence_1_to_3"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("event_evidence.id", ondelete="CASCADE"), index=True
    )
    annotator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    relation: Mapped[EvidenceRelation] = mapped_column(
        Enum(
            EvidenceRelation, name="evidence_relation", values_callable=_values, create_type=False
        )  # fmt: skip
    )
    conflicts: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    stale: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    confidence: Mapped[int] = mapped_column(SmallInteger, default=2, server_default="2")
    note: Mapped[str | None] = mapped_column(Text)
    blind: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false",
        doc="Made from the second-opinion queue, without seeing other labels",
    )  # fmt: skip
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    evidence: Mapped[EventEvidence] = relationship(back_populates="judgements")
    annotator = relationship("User", lazy="joined")
