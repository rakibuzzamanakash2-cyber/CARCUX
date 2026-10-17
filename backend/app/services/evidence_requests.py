"""Asking field workers to check an event, and closing the request (models/evidence_request.py)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.event import Event, EventStatus
from app.models.evidence_request import EvidenceRequest, RequestStatus
from app.models.field_report import FieldReport
from app.models.user import User
from app.services import audit


class EventClosedError(Exception):
    """Resolved or dismissed events are not checked again."""


class AlreadyOpenError(Exception):
    def __init__(self, request: EvidenceRequest):
        super().__init__("This event already has an open request")
        self.request = request


class NotOpenError(Exception):
    """The request was already closed."""


def open_request(db: Session, event_id: uuid.UUID) -> EvidenceRequest | None:
    return db.scalar(
        select(EvidenceRequest).where(
            EvidenceRequest.event_id == event_id, EvidenceRequest.status == RequestStatus.OPEN
        )
    )


def for_event(db: Session, event_id: uuid.UUID) -> list[EvidenceRequest]:
    return list(
        db.scalars(
            select(EvidenceRequest)
            .where(EvidenceRequest.event_id == event_id)
            .order_by(EvidenceRequest.created_at.desc())
        ).all()
    )


def create(
    db: Session, event: Event, actor: User, question: str, ip_address: str | None
) -> EvidenceRequest:
    if event.status in (EventStatus.RESOLVED, EventStatus.DISMISSED):
        raise EventClosedError
    existing = open_request(db, event.id)
    if existing is not None:
        raise AlreadyOpenError(existing)
    request = EvidenceRequest(event_id=event.id, question=question.strip(), created_by_id=actor.id)
    db.add(request)
    try:
        db.flush()
    except IntegrityError:  # another analyst opened one at the same moment
        db.rollback()
        raise AlreadyOpenError(open_request(db, event.id)) from None
    audit.record(
        db,
        audit.AuditAction.EVIDENCE_REQUESTED,
        actor_id=actor.id,
        target_type="event",
        target_id=event.id,
        ip_address=ip_address,
        details={"request_id": str(request.id), "question": request.question},
    )
    db.commit()
    db.refresh(request)
    return request


def close(
    db: Session,
    request: EvidenceRequest,
    actor: User,
    status: RequestStatus,
    note: str | None,
    ip_address: str | None,
) -> EvidenceRequest:
    if request.status != RequestStatus.OPEN:
        raise NotOpenError
    request.status = status
    request.closed_by_id = actor.id
    request.closed_at = datetime.now(UTC)
    request.close_note = note.strip() if note and note.strip() else None
    audit.record(
        db,
        audit.AuditAction.EVIDENCE_REQUEST_CLOSED,
        actor_id=actor.id,
        target_type="event",
        target_id=request.event_id,
        ip_address=ip_address,
        details={
            "request_id": str(request.id),
            "status": status.value,
            "responses": len(request.responses),
        },
    )
    db.commit()
    db.refresh(request)
    return request


def close_with_event(db: Session, event: Event, actor: User) -> None:
    """When an event is resolved or dismissed, its open request is cancelled with it
    (the caller commits)."""
    request = open_request(db, event.id)
    if request is None:
        return
    request.status = RequestStatus.CANCELLED
    request.closed_by_id = actor.id
    request.closed_at = datetime.now(UTC)
    request.close_note = f"The event was marked {event.status.value}."


def open_for_workers(db: Session, worker: User) -> list[tuple[EvidenceRequest, int]]:
    """Open requests, newest first, with how many reports this worker already sent."""
    mine = (
        select(FieldReport.request_id, func.count().label("n"))
        .where(FieldReport.reporter_id == worker.id, FieldReport.request_id.is_not(None))
        .group_by(FieldReport.request_id)
        .subquery()
    )
    rows = db.execute(
        select(EvidenceRequest, func.coalesce(mine.c.n, 0))
        .outerjoin(mine, mine.c.request_id == EvidenceRequest.id)
        .where(EvidenceRequest.status == RequestStatus.OPEN)
        .order_by(EvidenceRequest.created_at.desc())
    ).all()
    return [(r, int(n)) for r, n in rows]
