"""Official statements: published by officials of verified pages, read by everyone
signed in (part 3 opens them to the public)."""

import uuid

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, client_ip
from app.models.event import Event
from app.models.official import OfficialPage, PageStatus
from app.models.statement import Statement
from app.models.user import Role, User
from app.schemas.statement import (
    EventLite,
    PageLite,
    StatementCreate,
    StatementDetail,
    StatementRead,
)
from app.services import statements as service

router = APIRouter(tags=["statements"])


def _read(st: Statement, user: User, later: dict, *, detail: bool = False):
    own = user.role == Role.ADMIN or user.official_page_id == st.page_id
    fields = dict(
        id=st.id, page=PageLite.model_validate(st.page), event=EventLite.model_validate(st.event),
        finding=st.finding, title=st.title, body=st.body, published_at=st.published_at,
        informed_by_carcux=st.informed_by_carcux, supersedes_id=st.supersedes_id,
        superseded_by_id=later.get(st.id), author=st.author.full_name if own else None,
    )  # fmt: skip
    return StatementDetail(**fields, brief=st.brief) if detail else StatementRead(**fields)


def _event_or_404(db, event_id: uuid.UUID) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    return event


@router.get("/events/{event_id}/brief")
def event_brief(event_id: uuid.UUID, db: DbSession, user: CurrentUser) -> dict:
    """What CARCUX knows about the event, for an official writing a statement (and for
    analysts and admins, to see what officials see)."""
    if not (service.can_write(user) or user.role in (Role.ADMIN, Role.ANALYST)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    return service.brief(db, _event_or_404(db, event_id))


@router.post("/statements", response_model=StatementDetail, status_code=status.HTTP_201_CREATED)
def publish(body: StatementCreate, request: Request, db: DbSession, user: CurrentUser):
    if not service.can_write(user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only officials of a verified page can publish statements"
        )
    try:
        st = service.publish(
            db, author=user, event=_event_or_404(db, body.event_id), finding=body.finding,
            title=body.title, body=body.body, supersedes_id=body.supersedes_id,
            ip=client_ip(request),
        )  # fmt: skip
    except service.StatementError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    db.commit()
    return _read(st, user, {}, detail=True)


@router.get("/statements", response_model=list[StatementRead])
def list_statements(
    db: DbSession,
    user: CurrentUser,
    event_id: uuid.UUID | None = None,
    page_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
):
    """Newest first. Statements of suspended or unverified pages only for admins and the
    page's own officials."""
    query = select(Statement).join(OfficialPage).order_by(Statement.published_at.desc())
    if event_id:
        query = query.where(Statement.event_id == event_id)
    if page_id:
        query = query.where(Statement.page_id == page_id)
    if user.role != Role.ADMIN:
        allowed = OfficialPage.status == PageStatus.VERIFIED
        if user.official_page_id:
            allowed = allowed | (Statement.page_id == user.official_page_id)
        query = query.where(allowed)
    rows = db.scalars(query.limit(limit)).unique().all()
    later = service.superseded_by(db, [s.id for s in rows])
    return [_read(s, user, later) for s in rows]


@router.get("/statements/{statement_id}", response_model=StatementDetail)
def get_statement(statement_id: uuid.UUID, db: DbSession, user: CurrentUser):
    st = db.get(Statement, statement_id)
    if st is None or not service.visible(st, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Statement not found")
    return _read(st, user, service.superseded_by(db, [st.id]), detail=True)
