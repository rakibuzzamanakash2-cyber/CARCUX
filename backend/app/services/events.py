"""Events, their evidence, and rule-based matching between reports and events.

The matching here is a transparent baseline: same area (5 km) and overlapping time
(48 h either side). It only *suggests*; an analyst decides. The learned correlation
engine (ai/correlation/) will replace the suggestions and can be evaluated against
the links analysts make here.
"""

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.event_types import EVENT_TYPE_FAMILY
from app.models.audit import AuditLog
from app.models.event import Event, EventEvidence, EventStatus, EvidenceRelation, Priority
from app.models.field_report import FieldReport, ReportStatus
from app.models.user import User
from app.services import audit
from app.services.integrity import haversine_km

MATCH_RADIUS_KM = 5.0


def escape_like(text: str) -> str:
    """Make user text safe inside a LIKE pattern (backslash is the escape character)."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


MATCH_WINDOW = timedelta(hours=48)


class ReportsNotFoundError(Exception):
    def __init__(self, missing: list[uuid.UUID]):
        self.missing = missing
        super().__init__(", ".join(str(m) for m in missing))


class AlreadyLinkedError(Exception):
    """This report is already evidence for this event."""


class InvalidTimesError(Exception):
    """ended_at is before started_at."""


# --- Events --------------------------------------------------------------------------


def create_event(
    db: Session,
    *,
    actor: User,
    data: dict[str, Any],
    field_report_ids: list[uuid.UUID],
    ip_address: str | None,
) -> Event:
    """Create an event, optionally attaching reports as supporting evidence."""
    report_ids = list(dict.fromkeys(field_report_ids))  # de-duplicate, keep order
    reports = _load_reports(db, report_ids)

    event = Event(
        id=uuid.uuid4(),
        family=EVENT_TYPE_FAMILY[data["event_type"]],
        created_by_id=actor.id,
        **data,
    )
    db.add(event)
    db.flush()
    audit.record(
        db,
        audit.AuditAction.EVENT_CREATED,
        actor_id=actor.id,
        target_type="event",
        target_id=event.id,
        ip_address=ip_address,
        details={"title": event.title, "event_type": event.event_type, "reports": len(reports)},
    )
    for report in reports:
        _attach(db, actor, event, report, EvidenceRelation.SUPPORTS, None, ip_address)
    db.commit()
    db.refresh(event)
    return event


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def update_event(
    db: Session,
    *,
    actor: User,
    event: Event,
    changes: dict[str, Any],
    ip_address: str | None,
) -> Event:
    """Apply changes and audit-log exactly what changed (old and new values)."""
    started = changes.get("started_at", event.started_at)
    ended = changes.get("ended_at", event.ended_at)
    if ended is not None and ended < started:
        raise InvalidTimesError

    diff: dict[str, list[Any]] = {}
    for field, new in changes.items():
        old = getattr(event, field)
        if old != new:
            diff[field] = [_jsonable(old), _jsonable(new)]
            setattr(event, field, new)
    if "event_type" in diff:
        event.family = EVENT_TYPE_FAMILY[event.event_type]

    if diff:
        audit.record(
            db,
            audit.AuditAction.EVENT_UPDATED,
            actor_id=actor.id,
            target_type="event",
            target_id=event.id,
            ip_address=ip_address,
            details={"changes": diff},
        )
        db.commit()
        db.refresh(event)
    return event


def list_events(
    db: Session,
    *,
    statuses: list[EventStatus] | None,
    family: str | None,
    limit: int,
    offset: int,
    priorities: list[Priority] | None = None,
    search: str | None = None,
) -> tuple[list[Event], int]:
    query = select(Event)
    if statuses:
        query = query.where(Event.status.in_(statuses))
    if family:
        query = query.where(Event.family == family)
    if priorities:
        query = query.where(Event.priority.in_(priorities))
    if search:
        pattern = f"%{escape_like(search)}%"
        query = query.where(
            or_(
                Event.title.ilike(pattern, escape="\\"),
                Event.place_name.ilike(pattern, escape="\\"),
                Event.summary.ilike(pattern, escape="\\"),
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(Event.started_at.desc(), Event.id).limit(limit).offset(offset)
    ).all()
    return list(items), total


def history(db: Session, event: Event) -> list[tuple[AuditLog, User | None]]:
    """Every recorded change to the event and its evidence, oldest first."""
    rows = db.execute(
        select(AuditLog, User)
        .outerjoin(User, User.id == AuditLog.actor_id)
        .where(AuditLog.target_type == "event", AuditLog.target_id == str(event.id))
        .order_by(AuditLog.occurred_at, AuditLog.id)
    ).all()
    return [(row[0], row[1]) for row in rows]


# --- Evidence ------------------------------------------------------------------------


def _load_reports(db: Session, ids: list[uuid.UUID]) -> list[FieldReport]:
    if not ids:
        return []
    found = {r.id: r for r in db.scalars(select(FieldReport).where(FieldReport.id.in_(ids)))}
    missing = [i for i in ids if i not in found]
    if missing:
        raise ReportsNotFoundError(missing)
    return [found[i] for i in ids]


def _attach(
    db: Session,
    actor: User,
    event: Event,
    report: FieldReport,
    relation: EvidenceRelation,
    note: str | None,
    ip_address: str | None,
) -> EventEvidence:
    item = EventEvidence(
        id=uuid.uuid4(),
        event_id=event.id,
        field_report_id=report.id,
        relation=relation,
        note=note,
        linked_by_id=actor.id,
    )
    db.add(item)
    # A report someone has placed against an event has been looked at.
    if report.status == ReportStatus.SUBMITTED:
        report.status = ReportStatus.REVIEWED
        report.reviewed_by_id = actor.id
        report.reviewed_at = datetime.now(UTC)
    audit.record(
        db,
        audit.AuditAction.EVIDENCE_LINKED,
        actor_id=actor.id,
        target_type="event",
        target_id=event.id,
        ip_address=ip_address,
        details={
            "evidence_id": str(item.id),
            "field_report_id": str(report.id),
            "relation": relation.value,
        },
    )
    return item


def link_report(
    db: Session,
    *,
    actor: User,
    event: Event,
    report_id: uuid.UUID,
    relation: EvidenceRelation,
    note: str | None,
    ip_address: str | None,
) -> EventEvidence:
    (report,) = _load_reports(db, [report_id])
    if any(e.field_report_id == report_id for e in event.evidence):
        raise AlreadyLinkedError
    item = _attach(db, actor, event, report, relation, note, ip_address)
    try:
        db.commit()
    except IntegrityError:  # linked concurrently by someone else
        db.rollback()
        raise AlreadyLinkedError from None
    db.refresh(item)
    db.refresh(event)
    return item


def update_evidence(
    db: Session,
    *,
    actor: User,
    item: EventEvidence,
    changes: dict[str, Any],
    ip_address: str | None,
) -> EventEvidence:
    diff = {}
    for field, new in changes.items():
        old = getattr(item, field)
        if old != new:
            diff[field] = [_jsonable(old), _jsonable(new)]
            setattr(item, field, new)
    if diff:
        audit.record(
            db,
            audit.AuditAction.EVIDENCE_UPDATED,
            actor_id=actor.id,
            target_type="event",
            target_id=item.event_id,
            ip_address=ip_address,
            details={
                "evidence_id": str(item.id),
                "field_report_id": str(item.field_report_id),
                "changes": diff,
            },
        )
        db.commit()
        db.refresh(item)
    return item


def unlink(db: Session, *, actor: User, item: EventEvidence, ip_address: str | None) -> None:
    audit.record(
        db,
        audit.AuditAction.EVIDENCE_UNLINKED,
        actor_id=actor.id,
        target_type="event",
        target_id=item.event_id,
        ip_address=ip_address,
        details={
            "evidence_id": str(item.id),
            "field_report_id": str(item.field_report_id),
            "relation": item.relation.value,
        },
    )
    db.delete(item)
    db.commit()


def links_for_report(db: Session, report_id: uuid.UUID) -> list[EventEvidence]:
    return list(
        db.scalars(
            select(EventEvidence)
            .where(EventEvidence.field_report_id == report_id)
            .order_by(EventEvidence.linked_at)
        )
    )


# --- Matching ------------------------------------------------------------------------


@dataclass(frozen=True)
class Match:
    distance_km: float
    hours_apart: float


def _bbox(lat: float, lon: float, km: float) -> tuple[float, float]:
    """Degrees of latitude and longitude spanning `km` around a point."""
    return km / 110.574, km / (111.320 * math.cos(math.radians(lat)))


def _hours_outside(moment: datetime, start: datetime, end: datetime) -> float:
    """0 if moment is within [start, end], else hours to the nearest edge."""
    if moment < start:
        return (start - moment).total_seconds() / 3600
    if moment > end:
        return (moment - end).total_seconds() / 3600
    return 0.0


def candidate_events(
    db: Session, report: FieldReport, *, limit: int = 10
) -> list[tuple[Event, Match]]:
    """Events this report may belong to: within 5 km, and the report falls within
    48 h of the event's time span (an open event runs until now). Not dismissed,
    not already linked. Same type first, then nearest."""
    now = datetime.now(UTC)
    dlat, dlon = _bbox(report.latitude, report.longitude, MATCH_RADIUS_KM)
    linked = select(EventEvidence.event_id).where(EventEvidence.field_report_id == report.id)
    events = db.scalars(
        select(Event).where(
            Event.status != EventStatus.DISMISSED,
            Event.id.not_in(linked),
            Event.latitude.between(report.latitude - dlat, report.latitude + dlat),
            Event.longitude.between(report.longitude - dlon, report.longitude + dlon),
            Event.started_at <= report.observed_at + MATCH_WINDOW,
            func.coalesce(Event.ended_at, now) >= report.observed_at - MATCH_WINDOW,
        )
    ).all()

    matches = []
    for event in events:
        km = haversine_km(report.latitude, report.longitude, event.latitude, event.longitude)
        if km > MATCH_RADIUS_KM:
            continue
        hours = _hours_outside(report.observed_at, event.started_at, event.ended_at or now)
        matches.append((event, Match(round(km, 2), round(hours, 1))))
    matches.sort(key=lambda m: (m[0].event_type != report.event_type, m[1].distance_km))
    return matches[:limit]


def candidate_reports(
    db: Session, event: Event, *, limit: int = 25
) -> list[tuple[FieldReport, Match]]:
    """Reports that may be evidence for this event, by the same rule as
    candidate_events. Not dismissed, not already linked to this event."""
    now = datetime.now(UTC)
    dlat, dlon = _bbox(event.latitude, event.longitude, MATCH_RADIUS_KM)
    linked = select(EventEvidence.field_report_id).where(EventEvidence.event_id == event.id)
    end = event.ended_at or now
    reports = db.scalars(
        select(FieldReport).where(
            FieldReport.status != ReportStatus.DISMISSED,
            FieldReport.id.not_in(linked),
            FieldReport.latitude.between(event.latitude - dlat, event.latitude + dlat),
            FieldReport.longitude.between(event.longitude - dlon, event.longitude + dlon),
            FieldReport.observed_at.between(event.started_at - MATCH_WINDOW, end + MATCH_WINDOW),
        )
    ).all()

    matches = []
    for report in reports:
        km = haversine_km(report.latitude, report.longitude, event.latitude, event.longitude)
        if km > MATCH_RADIUS_KM:
            continue
        hours = _hours_outside(report.observed_at, event.started_at, end)
        matches.append((report, Match(round(km, 2), round(hours, 1))))
    matches.sort(key=lambda m: (m[0].event_type != event.event_type, m[1].distance_km))
    return matches[:limit]
