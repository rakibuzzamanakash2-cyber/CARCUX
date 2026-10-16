"""Public signals: alerts, bulletins and news items. Everyone signed in can read them;
analysts and admins enter bulletins, triage signals and link them to events."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, client_ip, require_roles
from app.api.suggestions import as_candidate
from app.core.event_types import EVENT_TYPE_FAMILY, EVENT_TYPES
from app.ingest import places
from app.models.event import Event, EvidenceRelation
from app.models.signal import Signal, SignalStatus, Source, SourceType
from app.models.user import Role, User
from app.schemas.event import CandidateEvent, EventRead, ReportLink
from app.schemas.signal import (
    District,
    ImportResultRead,
    ImportRow,
    LinkAdded,
    LinkCreate,
    LinkPreview,
    SignalCreate,
    SignalPage,
    SignalRead,
    SignalReview,
)
from app.services import events as event_service
from app.services import links, signal_import
from app.services import signals as service
from app.services import suggest as suggest_service
from app.services.details import headline_and_text

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


@router.get("/links/preview", response_model=LinkPreview)
def preview_link(db: DbSession, _user: Reviewer, url: Annotated[str, Query(max_length=1000)]):
    """What a pasted link says about itself, and whether it is already in CARCUX. The
    link is not opened."""
    try:
        link = links.parse(url)
    except links.BadLinkError as exc:
        raise _unprocessable(str(exc)) from None
    existing = service.find_link(db, link)
    known = None
    if link.platform is links.WEB:
        src = db.scalar(
            select(Source).where(Source.domain.in_([link.domain, f"www.{link.domain}"])).limit(1)
        )
        known = src.name if src else None
    elif link.account:
        src = db.scalar(
            select(Source).where(
                Source.key == f"{link.platform.key}-{service._slug(link.account)}"[:40]
            )
        )
        known = src.name if src else None
    return LinkPreview(
        platform=link.platform.key,
        platform_label=link.platform.label,
        kind=SourceType(link.platform.kind),
        url=link.url,
        post_id=link.post_id,
        account=link.account,
        video=link.video,
        existing_signal_id=existing.id if existing else None,
        known_source=known,
    )


@router.post("/links", response_model=LinkAdded)
def add_link(body: LinkCreate, request: Request, response: Response, db: DbSession, user: Reviewer):
    """Add a post or article an analyst pasted (Facebook, YouTube, X, TikTok, Instagram,
    Telegram, any news site), with what it says. One source per account, so each page
    builds its own track record. The same post twice is one signal. 201 when new."""
    event = None
    if body.event_id is not None:
        event = db.get(Event, body.event_id)
        if event is None:
            raise _unprocessable("Event not found")
    try:
        signal, created = service.add_link(
            db, actor=user, data=body.model_dump(), ip_address=client_ip(request)
        )
    except (links.BadLinkError, service.LinkError) as exc:
        raise _unprocessable(str(exc)) from None
    except service.UnknownDistrictError:
        raise _unprocessable(f"Unknown district '{body.district}'") from None
    evidence_id, already = None, False
    if event is not None:
        try:
            item = event_service.link_signal(
                db, actor=user, event=event, signal_id=signal.id,
                relation=EvidenceRelation(body.relation), note=None,
                ip_address=client_ip(request),
            )  # fmt: skip
            evidence_id = item.id
        except event_service.AlreadyLinkedError:
            already = True
    if created:
        response.status_code = status.HTTP_201_CREATED
    db.refresh(signal)
    return LinkAdded(
        signal=SignalRead.model_validate(signal),
        created=created,
        evidence_id=evidence_id,
        already_linked=already,
    )


@router.post("/import", response_model=ImportResultRead)
async def import_list(
    request: Request,
    db: DbSession,
    user: Reviewer,
    file: Annotated[UploadFile, File(description="CSV, UTF-8, with a header row")],
    dry_run: Annotated[bool, Query(description="Check the file without saving")] = True,
):
    """Import past news items collected by annotators. Check first (dry_run), then save."""
    data = await file.read(signal_import.MAX_BYTES + 1)
    try:
        result = signal_import.import_csv(
            db, actor=user, data=data, dry_run=dry_run, ip_address=client_ip(request)
        )
    except signal_import.ImportFileError as exc:
        db.rollback()
        raise _unprocessable(str(exc)) from None
    return ImportResultRead(
        dry_run=dry_run,
        added=result.count("add"),
        duplicates=result.count("duplicate"),
        errors=result.count("error"),
        new_publishers=result.created_sources,
        rows=[ImportRow(**r.__dict__) for r in result.rows],
    )


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
    """Events this signal may be about, ranked: suggestions only. By area and time
    overlap until a suggestion model is trained, then by the model (see /suggestions)."""
    signal = _signal_or_404(db, signal_id)
    text = headline_and_text(signal.title, signal.text)
    return [
        as_candidate(s, db, text, signal.event_type, signal.published_at)
        for s in suggest_service.for_signal(db, signal)
    ]


@places_router.get("/districts", response_model=list[District])
def districts(_user: CurrentUser):
    """The 64 districts and their centres, for placing bulletins."""
    return places.districts()
