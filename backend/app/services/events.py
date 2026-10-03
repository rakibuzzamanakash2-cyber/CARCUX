"""Events, their evidence, and rule-based matching between evidence and events.

Evidence is a field report or a public signal (alert, bulletin, news item).

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
from app.models.signal import Signal, SignalStatus
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


class SignalsNotFoundError(Exception):
    def __init__(self, missing: list[uuid.UUID]):
        self.missing = missing
        super().__init__(", ".join(str(m) for m in missing))


class AlreadyLinkedError(Exception):
    """This report or signal is already evidence for this event."""


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
    signal_ids: list[uuid.UUID] | None = None,
) -> Event:
    """Create an event, optionally attaching reports and signals as supporting evidence."""
    report_ids = list(dict.fromkeys(field_report_ids))  # de-duplicate, keep order
    reports = _load_reports(db, report_ids)
    signals = _load_signals(db, list(dict.fromkeys(signal_ids or [])))

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
        details={
            "title": event.title,
            "event_type": event.event_type,
            "reports": len(reports),
            "signals": len(signals),
        },
    )
    for report in reports:
        _attach(db, actor, event, EvidenceRelation.SUPPORTS, None, ip_address, report=report)
    for signal in signals:
        _attach(db, actor, event, EvidenceRelation.SUPPORTS, None, ip_address, signal=signal)
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


def _load_signals(db: Session, ids: list[uuid.UUID]) -> list[Signal]:
    if not ids:
        return []
    found = {s.id: s for s in db.scalars(select(Signal).where(Signal.id.in_(ids)))}
    missing = [i for i in ids if i not in found]
    if missing:
        raise SignalsNotFoundError(missing)
    return [found[i] for i in ids]


def evidence_ref(item: EventEvidence) -> dict[str, str]:
    """What the evidence is, for audit details: the report or the signal."""
    if item.signal_id is not None:
        return {"signal_id": str(item.signal_id)}
    return {"field_report_id": str(item.field_report_id)}


def _attach(
    db: Session,
    actor: User,
    event: Event,
    relation: EvidenceRelation,
    note: str | None,
    ip_address: str | None,
    *,
    report: FieldReport | None = None,
    signal: Signal | None = None,
) -> EventEvidence:
    item = EventEvidence(
        id=uuid.uuid4(),
        event_id=event.id,
        field_report_id=report.id if report else None,
        signal_id=signal.id if signal else None,
        relation=relation,
        note=note,
        linked_by_id=actor.id,
    )
    db.add(item)
    # Evidence someone has placed against an event has been looked at.
    now = datetime.now(UTC)
    if report is not None and report.status == ReportStatus.SUBMITTED:
        report.status = ReportStatus.REVIEWED
        report.reviewed_by_id = actor.id
        report.reviewed_at = now
    if signal is not None and signal.status == SignalStatus.NEW:
        signal.status = SignalStatus.REVIEWED
        signal.reviewed_by_id = actor.id
        signal.reviewed_at = now
    audit.record(
        db,
        audit.AuditAction.EVIDENCE_LINKED,
        actor_id=actor.id,
        target_type="event",
        target_id=event.id,
        ip_address=ip_address,
        details={"evidence_id": str(item.id), **evidence_ref(item), "relation": relation.value},
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
    item = _attach(db, actor, event, relation, note, ip_address, report=report)
    return _commit_link(db, event, item)


def link_signal(
    db: Session,
    *,
    actor: User,
    event: Event,
    signal_id: uuid.UUID,
    relation: EvidenceRelation,
    note: str | None,
    ip_address: str | None,
) -> EventEvidence:
    (signal,) = _load_signals(db, [signal_id])
    if any(e.signal_id == signal_id for e in event.evidence):
        raise AlreadyLinkedError
    item = _attach(db, actor, event, relation, note, ip_address, signal=signal)
    return _commit_link(db, event, item)


def _commit_link(db: Session, event: Event, item: EventEvidence) -> EventEvidence:
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
            details={"evidence_id": str(item.id), **evidence_ref(item), "changes": diff},
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
            **evidence_ref(item),
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


def links_for_signal(db: Session, signal_id: uuid.UUID) -> list[EventEvidence]:
    return list(
        db.scalars(
            select(EventEvidence)
            .where(EventEvidence.signal_id == signal_id)
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


# --- Matching signals ----------------------------------------------------------------
#
# Same rule, widened by the signal's own uncertainty: a news item placed at a district
# centre (30 km) matches events anywhere in that district; a GDACS flood alert covers
# its whole area. Time is the signal's validity (or its publication) within 48 h of
# the event's span.

MAX_SIGNAL_REACH_KM = 300.0


def _reach_km(signal: Signal) -> float:
    return MATCH_RADIUS_KM + min((signal.precision_m or 0) / 1000, MAX_SIGNAL_REACH_KM)


def _signal_span(signal: Signal) -> tuple[datetime, datetime]:
    start = signal.valid_from or signal.published_at
    end = signal.valid_until or signal.published_at
    return (start, end) if end >= start else (end, start)


def _gap_hours(a: tuple[datetime, datetime], b: tuple[datetime, datetime]) -> float:
    """0 if the spans overlap, else hours between them."""
    if a[1] < b[0]:
        return (b[0] - a[1]).total_seconds() / 3600
    if b[1] < a[0]:
        return (a[0] - b[1]).total_seconds() / 3600
    return 0.0


def candidate_events_for_signal(
    db: Session, signal: Signal, *, limit: int = 10
) -> list[tuple[Event, Match]]:
    """Open or recent events this signal may be about. Needs the signal's location."""
    if signal.latitude is None or signal.longitude is None:
        return []
    now = datetime.now(UTC)
    reach = _reach_km(signal)
    dlat, dlon = _bbox(signal.latitude, signal.longitude, reach)
    start, end = _signal_span(signal)
    linked = select(EventEvidence.event_id).where(EventEvidence.signal_id == signal.id)
    events = db.scalars(
        select(Event).where(
            Event.status != EventStatus.DISMISSED,
            Event.id.not_in(linked),
            Event.latitude.between(signal.latitude - dlat, signal.latitude + dlat),
            Event.longitude.between(signal.longitude - dlon, signal.longitude + dlon),
            Event.started_at <= end + MATCH_WINDOW,
            func.coalesce(Event.ended_at, now) >= start - MATCH_WINDOW,
        )
    ).all()
    matches = []
    for event in events:
        km = haversine_km(signal.latitude, signal.longitude, event.latitude, event.longitude)
        if km > reach:
            continue
        hours = _gap_hours((start, end), (event.started_at, event.ended_at or now))
        matches.append((event, Match(round(km, 2), round(hours, 1))))
    matches.sort(key=lambda m: (m[0].event_type != signal.event_type, m[1].distance_km))
    return matches[:limit]


def candidate_signals(db: Session, event: Event, *, limit: int = 25) -> list[tuple[Signal, Match]]:
    """Signals that may be about this event: placed, not dismissed, not yet linked."""
    now = datetime.now(UTC)
    end = event.ended_at or now
    widest = MATCH_RADIUS_KM + MAX_SIGNAL_REACH_KM
    dlat, dlon = _bbox(event.latitude, event.longitude, widest)
    linked = select(EventEvidence.signal_id).where(
        EventEvidence.event_id == event.id, EventEvidence.signal_id.is_not(None)
    )
    signals = db.scalars(
        select(Signal).where(
            Signal.status != SignalStatus.DISMISSED,
            Signal.id.not_in(linked),
            Signal.latitude.between(event.latitude - dlat, event.latitude + dlat),
            Signal.longitude.between(event.longitude - dlon, event.longitude + dlon),
            func.coalesce(Signal.valid_from, Signal.published_at) <= end + MATCH_WINDOW,
            func.coalesce(Signal.valid_until, Signal.published_at)
            >= event.started_at - MATCH_WINDOW,
        )
    ).all()
    matches = []
    for signal in signals:
        km = haversine_km(signal.latitude, signal.longitude, event.latitude, event.longitude)
        if km > _reach_km(signal):
            continue
        hours = _gap_hours(_signal_span(signal), (event.started_at, end))
        matches.append((signal, Match(round(km, 2), round(hours, 1))))
    matches.sort(key=lambda m: (m[0].event_type != event.event_type, m[1].distance_km))
    return matches[:limit]
