"""Public signals: alerts, bulletins and news items. Everyone signed in can read them;
analysts and admins enter bulletins, triage signals and link them to events."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import CurrentUser, DbSession, client_ip, require_roles
from app.core.event_types import EVENT_TYPE_FAMILY, EVENT_TYPES
from app.ingest import places
from app.models.signal import Signal, SignalStatus, Source
from app.models.user import Role, User
from app.schemas.event import CandidateEvent, EventRead, ReportLink
from app.schemas.signal import District, SignalCreate, SignalPage, SignalRead, SignalReview
from app.services import events as event_service
from app.services import signals as service

router = APIRouter(prefix="/signals", tags=["signals"])
places_router = APIRouter(prefix="/places", tags=["signals"])

Reviewer = Annotated[User, Depends(require_roles(Role.ANALYST, Role.ADMIN))]
FAMILIES = sorted(set(EVENT_TYPE_FAMILY.values()))


def _unprocessable(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


def _signal_or_404(db, signal_id: uuid.UUID) -> Signal:
    signal = db.get(Signal, signal_id)
    if signal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Signal not found")
    return signal


@router.get("", response_model=SignalPage)
def list_signals(
    db: DbSession,
    _user: CurrentUser,
    source: Annotated[
        list[uuid.UUID] | None, Query(description="Source id; repeat for several")
    ] = None,
    status_: Annotated[
        list[SignalStatus] | None,
        Query(alias="status", description="Repeat to include several; default all"),
    ] = None,
    family: Annotated[str | None, Query(description=f"One of: {', '.join(FAMILIES)}")] = None,
    event_type: str | None = None,
    q: Annotated[
        str | None, Query(max_length=100, description="Words in title, text, place")
    ] = None,
    since: Annotated[datetime | None, Query(description="Published at or after")] = None,
    located: Annotated[bool | None, Query(description="Only with (or without) a place")] = None,
    order: Literal["newest", "oldest"] = "newest",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    if family is not None and family not in FAMILIES:
        raise _unprocessable(f"Unknown family '{family}'")
    if event_type is not None and event_type not in EVENT_TYPES:
        raise _unprocessable(f"Unknown event_type '{event_type}'")
    if since is not None and since.tzinfo is None:
        raise _unprocessable("since must include a UTC offset, e.g. +06:00")
    items, total = service.list_signals(
        db,
        limit=limit,
        offset=offset,
        source_ids=source,
        statuses=status_,
        family=family,
        event_type=event_type,
        search=q.strip() if q and q.strip() else None,
        since=since,
        located=located,
        order=order,
    )
    return SignalPage(
        items=[SignalRead.model_validate(s) for s in items], total=total, limit=limit, offset=offset
    )


@router.post("", response_model=SignalRead, status_code=status.HTTP_201_CREATED)
def enter_bulletin(body: SignalCreate, request: Request, db: DbSession, user: Reviewer):
    """Enter a bulletin by hand, for a source without a feed (BMD, FFWC)."""
    source = db.get(Source, body.source_id)
    if source is None:
        raise _unprocessable("Source not found")
    try:
        return service.enter_bulletin(
            db,
            actor=user,
            source=source,
            data=body.model_dump(exclude={"source_id"}),
            ip_address=client_ip(request),
        )
    except service.NotManualSourceError:
        raise _unprocessable(f"{source.name} is read automatically; pick a manual source") from None
    except service.UnknownDistrictError:
        raise _unprocessable(f"Unknown district '{body.district}'") from None


@router.get("/{signal_id}", response_model=SignalRead)
def get_signal(signal_id: uuid.UUID, db: DbSession, _user: CurrentUser):
    return _signal_or_404(db, signal_id)


@router.post("/{signal_id}/review", response_model=SignalRead)
def review_signal(
    signal_id: uuid.UUID, body: SignalReview, request: Request, db: DbSession, user: Reviewer
):
    """Mark reviewed, dismiss with a reason, or put back as new."""
    return service.review(
        db,
        actor=user,
        signal=_signal_or_404(db, signal_id),
        status=body.status,
        note=body.note,
        ip_address=client_ip(request),
    )


@router.get("/{signal_id}/events", response_model=list[ReportLink])
def signal_events(signal_id: uuid.UUID, db: DbSession, _user: Reviewer):
    """Events this signal is evidence for, and how."""
    _signal_or_404(db, signal_id)
    return [
        ReportLink(
            evidence_id=item.id, relation=item.relation, event=EventRead.model_validate(item.event)
        )
        for item in event_service.links_for_signal(db, signal_id)
    ]


@router.get("/{signal_id}/candidate-events", response_model=list[CandidateEvent])
def candidate_events(signal_id: uuid.UUID, db: DbSession, _user: Reviewer):
    """Events whose area and time overlap the signal's: suggestions only."""
    signal = _signal_or_404(db, signal_id)
    return [
        CandidateEvent(
            event=EventRead.model_validate(event),
            distance_km=m.distance_km,
            hours_apart=m.hours_apart,
            same_type=event.event_type == signal.event_type,
            same_family=signal.family is not None and event.family == signal.family,
        )
        for event, m in event_service.candidate_events_for_signal(db, signal)
    ]


@places_router.get("/districts", response_model=list[District])
def districts(_user: CurrentUser):
    """The 64 districts and their centres, for placing bulletins."""
    return places.districts()
