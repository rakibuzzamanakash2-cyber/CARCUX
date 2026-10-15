"""Events: everyone signed in can read them; analysts and admins manage them and their evidence."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.api.deps import CurrentUser, DbSession, client_ip, require_roles
from app.core.event_types import EVENT_TYPE_FAMILY
from app.models.event import Event, EventEvidence, EventStatus, Priority
from app.models.user import Role, User
from app.schemas.assessment import (
    AssessmentReason,
    AssessmentSuggestionRead,
    DetailSummaryRead,
    StatedValue,
)
from app.schemas.event import (
    CandidateReport,
    CandidateSignal,
    CopyDecisionIn,
    CopyRead,
    EventCreate,
    EventPage,
    EventRead,
    EventUpdate,
    EvidenceCreate,
    EvidenceRead,
    EvidenceUpdate,
    HistoryEntry,
    StanceQuery,
    StanceRead,
    stance_read,
)
from app.schemas.field_report import FieldReportRead, ReporterRead
from app.schemas.signal import SignalRead
from app.services import assess
from app.services import copies as copy_detection
from app.services import events as service
from app.services import stance as stance_service
from app.services.details import headline_and_text

router = APIRouter(prefix="/events", tags=["events"])

Reviewer = Annotated[User, Depends(require_roles(Role.ANALYST, Role.ADMIN))]

FAMILIES = sorted(set(EVENT_TYPE_FAMILY.values()))


def _event_or_404(db, event_id: uuid.UUID) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    return event


def _evidence_or_404(db, event: Event, evidence_id: uuid.UUID) -> EventEvidence:
    item = db.get(EventEvidence, evidence_id)
    if item is None or item.event_id != event.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evidence not found")
    return item


def _reports_missing(exc: service.ReportsNotFoundError) -> HTTPException:
    ids = ", ".join(str(m) for m in exc.missing)
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Field report not found: {ids}")


def _signals_missing(exc: service.SignalsNotFoundError) -> HTTPException:
    ids = ", ".join(str(m) for m in exc.missing)
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Signal not found: {ids}")


@router.get("", response_model=EventPage)
def list_events(
    db: DbSession,
    _user: CurrentUser,
    status_: Annotated[
        list[EventStatus] | None,
        Query(alias="status", description="Repeat to include several; default all"),
    ] = None,
    family: Annotated[str | None, Query(description=f"One of: {', '.join(FAMILIES)}")] = None,
    priority: Annotated[
        list[Priority] | None, Query(description="Repeat to include several; default all")
    ] = None,
    q: Annotated[
        str | None, Query(max_length=100, description="Words in the title, place or summary")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    if family is not None and family not in FAMILIES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown family '{family}'")
    items, total = service.list_events(
        db,
        statuses=status_,
        family=family,
        priorities=priority,
        search=q.strip() if q and q.strip() else None,
        limit=limit,
        offset=offset,
    )
    return EventPage(
        items=[EventRead.model_validate(e) for e in items], total=total, limit=limit, offset=offset
    )


@router.post("", response_model=EventRead, status_code=status.HTTP_201_CREATED)
def create_event(body: EventCreate, request: Request, db: DbSession, user: Reviewer):
    data = body.model_dump(exclude={"field_report_ids", "signal_ids"})
    try:
        return service.create_event(
            db,
            actor=user,
            data=data,
            field_report_ids=body.field_report_ids,
            signal_ids=body.signal_ids,
            ip_address=client_ip(request),
        )
    except service.ReportsNotFoundError as exc:
        db.rollback()
        raise _reports_missing(exc) from None
    except service.SignalsNotFoundError as exc:
        db.rollback()
        raise _signals_missing(exc) from None


@router.get("/{event_id}", response_model=EventRead)
def get_event(event_id: uuid.UUID, db: DbSession, _user: CurrentUser):
    return _event_or_404(db, event_id)


@router.patch("/{event_id}", response_model=EventRead)
def update_event(
    event_id: uuid.UUID, body: EventUpdate, request: Request, db: DbSession, user: Reviewer
):
    event = _event_or_404(db, event_id)
    try:
        return service.update_event(
            db, actor=user, event=event, changes=body.changes(), ip_address=client_ip(request)
        )
    except service.InvalidTimesError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "ended_at must not be before started_at"
        ) from None


@router.get("/{event_id}/assessment-suggestion", response_model=AssessmentSuggestionRead)
def assessment_suggestion(event_id: uuid.UUID, db: DbSession, _user: Reviewer):
    """The suggested assessment from the evidence linked so far, with the sources behind
    it. A suggestion only: the analyst sets the assessment."""
    s = assess.suggest(db, _event_or_404(db, event_id))
    return AssessmentSuggestionRead(
        label=s.label,
        probability=s.probability,
        method=s.method,
        model_id=s.model_id,
        sources_supporting=s.sources_supporting,
        sources_denying=s.sources_denying,
        credible_supporting=s.credible_supporting,
        credible_denying=s.credible_denying,
        disputed=s.disputed,
        disputed_detected=s.disputed_detected,
        counted_once=s.counted_once,
        details=[
            DetailSummaryRead(
                attribute=d.attribute,
                estimate=d.estimate,
                unit=d.unit,
                disputed=d.disputed,
                statements=[StatedValue(**vars(x)) for x in d.statements],
            )
            for d in s.details
        ],
        reasons=[
            AssessmentReason(
                source=r.source,
                kind=r.kind,
                vote=r.vote,
                reliability=r.reliability,
                learned=r.learned,
                disputed=list(r.disputed),
            )
            for r in s.reasons
        ],
    )


@router.get("/{event_id}/history", response_model=list[HistoryEntry])
def event_history(event_id: uuid.UUID, db: DbSession, _user: Reviewer):
    """Who changed what, and when: the event's slice of the audit log."""
    event = _event_or_404(db, event_id)
    return [
        HistoryEntry(
            occurred_at=entry.occurred_at,
            action=entry.action,
            actor=ReporterRead.model_validate(actor) if actor else None,
            details=entry.details,
        )
        for entry, actor in service.history(db, event)
    ]


# --- Evidence ------------------------------------------------------------------------


@router.get("/{event_id}/evidence", response_model=list[EvidenceRead])
def list_evidence(event_id: uuid.UUID, db: DbSession, _user: Reviewer):
    event = _event_or_404(db, event_id)
    found = copy_detection.resolved(db, event)
    out = []
    for link in event.evidence:
        item = EvidenceRead.model_validate(link)
        item.stance = stance_read(
            stance_service.suggest(db, event, _item_text(link), item_type=_item_type(link),
                                   exclude=link.id)
        )  # fmt: skip
        c = found.get(link.id)
        if c is not None:
            item.copy_of = CopyRead(
                origin_evidence_id=c.origin_evidence_id,
                origin_source=c.origin_source,
                kind=c.kind,
                text_similarity=c.text_similarity,
                reasons=c.reasons,
                status=c.status,
                decided_by=c.decided_by,
            )
        out.append(item)
    return out


def _item_text(link) -> str:
    if link.field_report is not None:
        return link.field_report.text
    return headline_and_text(link.signal.title, link.signal.text)


def _item_type(link) -> str | None:
    return (link.field_report or link.signal).event_type


@router.post("/{event_id}/stance", response_model=StanceRead)
def read_stance(event_id: uuid.UUID, body: StanceQuery, db: DbSession, _user: Reviewer):
    """How a text not yet in CARCUX (a link being added) reads toward the event."""
    event = _event_or_404(db, event_id)
    return stance_read(stance_service.suggest(db, event, body.text, item_type=body.event_type))


@router.put("/{event_id}/evidence/{evidence_id}/copy", status_code=204)
def decide_copy(
    event_id: uuid.UUID,
    evidence_id: uuid.UUID,
    body: CopyDecisionIn,
    request: Request,
    db: DbSession,
    user: Reviewer,
):
    """Confirm that a linked item copies another item of the same event (or name which),
    or say it is not a copy (`origin_evidence_id: null`). Overrides the detection."""
    event = _event_or_404(db, event_id)
    item = _evidence_or_404(db, event, evidence_id)
    try:
        copy_detection.decide(
            db,
            actor=user,
            event=event,
            item=item,
            origin_evidence_id=body.origin_evidence_id,
            ip_address=client_ip(request),
        )
    except copy_detection.NotInEventError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "The origin must be another item linked to this event",
        ) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{event_id}/evidence/{evidence_id}/copy", status_code=204)
def clear_copy_decision(
    event_id: uuid.UUID, evidence_id: uuid.UUID, request: Request, db: DbSession, user: Reviewer
):
    """Forget the analyst's decision: the automatic detection applies again."""
    event = _event_or_404(db, event_id)
    item = _evidence_or_404(db, event, evidence_id)
    copy_detection.clear(db, actor=user, event=event, item=item, ip_address=client_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{event_id}/evidence", response_model=EvidenceRead, status_code=status.HTTP_201_CREATED
)
def link_evidence(
    event_id: uuid.UUID, body: EvidenceCreate, request: Request, db: DbSession, user: Reviewer
):
    event = _event_or_404(db, event_id)
    common = {
        "actor": user,
        "event": event,
        "relation": body.relation,
        "note": body.note,
        "ip_address": client_ip(request),
        "labels": {
            "conflicts": [str(c) for c in body.conflicts],
            "stale": body.stale,
            "confidence": body.confidence,
        },
        "suggestion": body.suggestion.model_dump(mode="json") if body.suggestion else None,
    }
    kind = "report" if body.field_report_id else "signal"
    try:
        if body.field_report_id:
            return service.link_report(db, report_id=body.field_report_id, **common)
        return service.link_signal(db, signal_id=body.signal_id, **common)
    except service.ReportsNotFoundError as exc:
        raise _reports_missing(exc) from None
    except service.SignalsNotFoundError as exc:
        raise _signals_missing(exc) from None
    except service.AlreadyLinkedError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This {kind} is already evidence for this event; change its relation instead",
        ) from None


@router.patch("/{event_id}/evidence/{evidence_id}", response_model=EvidenceRead)
def update_evidence(
    event_id: uuid.UUID,
    evidence_id: uuid.UUID,
    body: EvidenceUpdate,
    request: Request,
    db: DbSession,
    user: Reviewer,
):
    item = _evidence_or_404(db, _event_or_404(db, event_id), evidence_id)
    try:
        return service.update_evidence(
            db,
            actor=user,
            item=item,
            changes=body.model_dump(exclude_unset=True),
            ip_address=client_ip(request),
        )
    except service.InvalidLabelsError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None


@router.delete("/{event_id}/evidence/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_evidence(
    event_id: uuid.UUID, evidence_id: uuid.UUID, request: Request, db: DbSession, user: Reviewer
):
    item = _evidence_or_404(db, _event_or_404(db, event_id), evidence_id)
    service.unlink(db, actor=user, item=item, ip_address=client_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{event_id}/candidate-reports", response_model=list[CandidateReport])
def candidate_reports(event_id: uuid.UUID, db: DbSession, _user: Reviewer):
    """Unlinked reports within 5 km and 48 h of the event: suggestions, not decisions."""
    event = _event_or_404(db, event_id)
    return [
        CandidateReport(
            report=FieldReportRead.model_validate(report),
            distance_km=m.distance_km,
            hours_apart=m.hours_apart,
            same_type=report.event_type == event.event_type,
            stance=stance_read(
                stance_service.suggest(db, event, report.text, item_type=report.event_type)
            ),
        )
        for report, m in service.candidate_reports(db, event)
    ]


@router.get("/{event_id}/candidate-signals", response_model=list[CandidateSignal])
def candidate_signals(event_id: uuid.UUID, db: DbSession, _user: Reviewer):
    """Unlinked signals whose area and time overlap the event's: suggestions only."""
    event = _event_or_404(db, event_id)
    return [
        CandidateSignal(
            signal=SignalRead.model_validate(signal),
            distance_km=m.distance_km,
            hours_apart=m.hours_apart,
            same_type=signal.event_type == event.event_type,
            stance=stance_read(
                stance_service.suggest(
                    db,
                    event,
                    headline_and_text(signal.title, signal.text),
                    item_type=signal.event_type,
                )
            ),
        )
        for signal, m in service.candidate_signals(db, event)
    ]
