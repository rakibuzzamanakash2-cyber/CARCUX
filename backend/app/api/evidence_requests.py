"""The review queue (which open events to check first) and requests for more evidence."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import DbSession, client_ip, require_roles
from app.models.event import Event
from app.models.evidence_request import EvidenceRequest, RequestStatus
from app.models.user import Role, User
from app.schemas.evidence_request import (
    CheckValueRead,
    EvidenceRequestClose,
    EvidenceRequestCreate,
    EvidenceRequestRead,
    OpenRequestBrief,
    QueueEvent,
    QueueItemRead,
    QueuePage,
    RequestForWorkers,
)
from app.services import evidence_requests as service
from app.services import triage

router = APIRouter(tags=["review queue"])
Reviewer = Annotated[User, Depends(require_roles(Role.ANALYST, Role.ADMIN))]
Worker = Annotated[User, Depends(require_roles(Role.FIELD_WORKER, Role.ANALYST, Role.ADMIN))]


def _item(i: triage.QueueItem) -> QueueItemRead:
    v = i.value
    r = i.open_request
    return QueueItemRead(
        event=QueueEvent.model_validate(i.event),
        suggested=i.suggested,
        differs=i.differs,
        value=CheckValueRead(
            probability=None if v.probability is None else round(v.probability, 4),
            if_supported=round(v.if_supported, 4),
            if_denied=round(v.if_denied, 4),
            chance_supported=round(v.chance_supported, 4),
            changes=round(v.changes, 4),
            uncertainty=round(v.uncertainty, 4),
        ),
        impact=i.impact,
        need=i.need,
        score=i.score,
        reasons=i.reasons,
        open_request=None
        if r is None
        else OpenRequestBrief(
            id=r.id, question=r.question, created_at=r.created_at, responses=len(r.responses)
        ),
        last_evidence_at=i.last_evidence_at,
    )


@router.get("/review-queue", response_model=QueuePage)
def review_queue(db: DbSession, _user: Reviewer, limit: Annotated[int, Query(ge=1, le=200)] = 50):
    """Open events, the ones where a check matters most first: impact (the priority the
    team set) times need (how uncertain the event is, and how likely one more field
    report is to change its assessment). Each item says why."""
    items, total = triage.queue(db, limit=limit)
    return QueuePage(items=[_item(i) for i in items], total=total)


@router.get("/review-queue/{event_id}", response_model=QueueItemRead)
def review_queue_item(event_id: uuid.UUID, db: DbSession, _user: Reviewer):
    """The same reading for one event (shown on its page), whatever its status."""
    item = triage.for_event(db, event_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    return _item(item)


@router.get("/events/{event_id}/evidence-requests", response_model=list[EvidenceRequestRead])
def event_requests(event_id: uuid.UUID, db: DbSession, _user: Reviewer):
    """Requests for this event, newest first, with the reports sent in answer."""
    if db.get(Event, event_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    return service.for_event(db, event_id)


@router.post(
    "/events/{event_id}/evidence-requests",
    response_model=EvidenceRequestRead,
    status_code=status.HTTP_201_CREATED,
)
def request_evidence(
    event_id: uuid.UUID, body: EvidenceRequestCreate, request: Request, db: DbSession,
    user: Reviewer,
):  # fmt: skip
    """Ask field workers to go and check. They see the question, place and kind of
    event, not the assessment. One open request per event."""
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    try:
        return service.create(db, event, user, body.question, client_ip(request))
    except service.EventClosedError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The event is resolved or dismissed; reopen it first."
        ) from None
    except service.AlreadyOpenError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This event already has an open request."
        ) from None


@router.post("/evidence-requests/{request_id}/close", response_model=EvidenceRequestRead)
def close_request(
    request_id: uuid.UUID, body: EvidenceRequestClose, request: Request, db: DbSession,
    user: Reviewer,
):  # fmt: skip
    found = db.get(EvidenceRequest, request_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    try:
        return service.close(
            db, found, user, RequestStatus(body.status), body.note, client_ip(request)
        )
    except service.NotOpenError:
        raise HTTPException(status.HTTP_409_CONFLICT, "This request is already closed.") from None


def _for_workers(r: EvidenceRequest, mine: int) -> RequestForWorkers:
    e = r.event
    return RequestForWorkers(
        id=r.id,
        question=r.question,
        event_type=e.event_type,
        place_name=e.place_name,
        latitude=e.latitude,
        longitude=e.longitude,
        created_at=r.created_at,
        answered_by_me=mine,
    )


@router.get("/evidence-requests/open", response_model=list[RequestForWorkers])
def open_requests(db: DbSession, user: Worker):
    """Open requests to check, newest first. Only what to check and where."""
    return [_for_workers(r, n) for r, n in service.open_for_workers(db, user)]


@router.get("/evidence-requests/{request_id}/brief", response_model=RequestForWorkers)
def request_brief(request_id: uuid.UUID, db: DbSession, user: Worker):
    """One open request as field workers see it (for the report form)."""
    for r, n in service.open_for_workers(db, user):
        if r.id == request_id:
            return _for_workers(r, n)
    raise HTTPException(status.HTTP_404_NOT_FOUND, "No open request with that id")
