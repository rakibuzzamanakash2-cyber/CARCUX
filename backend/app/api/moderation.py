"""Moderating the public side: admins see and act on every comment; officials on
comments under their own page's posts. Banning an account is for admins."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select

from app.api.deps import DbSession, client_ip, require_roles
from app.models.event import Event
from app.models.public import (
    CommentReport,
    IncidentOpinion,
    OpinionReport,
    PublicAccount,
    StatementComment,
)
from app.models.statement import Statement
from app.models.user import Role, User
from app.schemas.public import ModerationComment, Reason
from app.services import public as service

router = APIRouter(prefix="/moderation", tags=["moderation"])

Moderator = Annotated[User, Depends(require_roles(Role.ADMIN, Role.OFFICIAL))]
Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]


def _rows(db, comments: list[StatementComment]) -> list[ModerationComment]:
    ids = [c.id for c in comments]
    reasons: dict = {}
    for cid, reason in db.execute(
        select(CommentReport.comment_id, CommentReport.reason).where(
            CommentReport.comment_id.in_(ids)
        )
    ):
        reasons.setdefault(cid, []).append(reason)
    out = []
    for c in comments:
        st = db.get(Statement, c.statement_id)
        out.append(
            ModerationComment(
                id=c.id,
                statement_id=c.statement_id,
                statement_title=st.title,
                page_name=st.page.name,
                author=c.account.display_name,
                account_id=c.account_id,
                account_status=c.account.status.value,
                body=c.body,
                created_at=c.created_at,
                reports=len(reasons.get(c.id, [])),
                report_reasons=sorted(set(reasons.get(c.id, []))),
                hidden_at=c.hidden_at,
                hidden_reason=c.hidden_reason,
            )  # fmt: skip
        )
    return out


@router.get("/comments", response_model=list[ModerationComment])
def comments(
    db: DbSession,
    user: Moderator,
    state: Literal["reported", "hidden", "all"] = "reported",
    statement_id: uuid.UUID | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    """Reported: visible comments with reports, or hidden after reports and waiting."""
    query = select(StatementComment).join(Statement).order_by(StatementComment.created_at.desc())
    if user.role == Role.OFFICIAL:
        query = query.where(Statement.page_id == user.official_page_id)
    if statement_id:
        query = query.where(StatementComment.statement_id == statement_id)
    reported = (
        select(CommentReport.comment_id).group_by(CommentReport.comment_id).having(func.count() > 0)
    )
    if state == "reported":
        query = query.where(
            StatementComment.id.in_(reported),
            StatementComment.cleared_at.is_(None),
            StatementComment.hidden_by_id.is_(None),
        )
    elif state == "hidden":
        query = query.where(StatementComment.hidden_at.is_not(None))
    return _rows(db, list(db.scalars(query.limit(limit)).unique()))


def _comment_for(db, comment_id: uuid.UUID, user: User) -> StatementComment:
    c = db.get(StatementComment, comment_id)
    if c is None or not service.can_moderate(user, c, db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment not found")
    return c


@router.post("/comments/{comment_id}/hide", response_model=ModerationComment)
def hide(comment_id: uuid.UUID, body: Reason, request: Request, db: DbSession, user: Moderator):
    c = _comment_for(db, comment_id, user)
    service.hide(db, c, user, body.reason, client_ip(request))
    db.commit()
    return _rows(db, [c])[0]


@router.post("/comments/{comment_id}/restore", response_model=ModerationComment)
def restore(comment_id: uuid.UUID, request: Request, db: DbSession, user: Moderator):
    """Keep it up: unhide, and stop further reports from hiding it again."""
    c = _comment_for(db, comment_id, user)
    service.restore(db, c, user, client_ip(request))
    db.commit()
    return _rows(db, [c])[0]


@router.post("/accounts/{account_id}/ban", status_code=status.HTTP_204_NO_CONTENT)
def ban(account_id: uuid.UUID, body: Reason, request: Request, db: DbSession, admin: Admin):
    account = db.get(PublicAccount, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    service.ban(db, account, admin, body.reason, client_ip(request))
    db.commit()


@router.post("/accounts/{account_id}/unban", status_code=status.HTTP_204_NO_CONTENT)
def unban(account_id: uuid.UUID, request: Request, db: DbSession, admin: Admin):
    account = db.get(PublicAccount, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    service.unban(db, account, admin, client_ip(request))
    db.commit()


# --- Opinions on incidents (admins) --------------------------------------------------------


def _opinion_rows(db, opinions: list[IncidentOpinion]) -> list[ModerationComment]:
    reasons: dict = {}
    for oid, reason in db.execute(
        select(OpinionReport.opinion_id, OpinionReport.reason).where(
            OpinionReport.opinion_id.in_([o.id for o in opinions])
        )
    ):
        reasons.setdefault(oid, []).append(reason)
    out = []
    for o in opinions:
        ev = db.get(Event, o.event_id)
        out.append(
            ModerationComment(
                kind="opinion",
                id=o.id,
                statement_id=o.event_id,
                statement_title=ev.title,
                page_name="People's opinions",
                author=o.account.display_name,
                account_id=o.account_id,
                account_status=o.account.status.value,
                body=o.body,
                created_at=o.created_at,
                reports=len(reasons.get(o.id, [])),
                report_reasons=sorted(set(reasons.get(o.id, []))),
                hidden_at=o.hidden_at,
                hidden_reason=o.hidden_reason,
            )  # fmt: skip
        )
    return out


@router.get("/opinions", response_model=list[ModerationComment])
def opinions(
    db: DbSession,
    _admin: Admin,
    state: Literal["reported", "hidden", "all"] = "reported",
    limit: int = Query(100, ge=1, le=500),
):
    query = select(IncidentOpinion).order_by(IncidentOpinion.created_at.desc())
    reported = select(OpinionReport.opinion_id).distinct()
    if state == "reported":
        query = query.where(
            IncidentOpinion.id.in_(reported),
            IncidentOpinion.cleared_at.is_(None),
            IncidentOpinion.hidden_by_id.is_(None),
        )
    elif state == "hidden":
        query = query.where(IncidentOpinion.hidden_at.is_not(None))
    return _opinion_rows(db, list(db.scalars(query.limit(limit)).unique()))


def _opinion_or_404(db, opinion_id: uuid.UUID) -> IncidentOpinion:
    op = db.get(IncidentOpinion, opinion_id)
    if op is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Opinion not found")
    return op


@router.post("/opinions/{opinion_id}/hide", response_model=ModerationComment)
def hide_opinion(
    opinion_id: uuid.UUID, body: Reason, request: Request, db: DbSession, admin: Admin
):
    op = _opinion_or_404(db, opinion_id)
    service.hide_opinion(db, op, admin, body.reason, client_ip(request))
    db.commit()
    return _opinion_rows(db, [op])[0]


@router.post("/opinions/{opinion_id}/restore", response_model=ModerationComment)
def restore_opinion(opinion_id: uuid.UUID, request: Request, db: DbSession, admin: Admin):
    op = _opinion_or_404(db, opinion_id)
    service.restore_opinion(db, op, admin, client_ip(request))
    db.commit()
    return _opinion_rows(db, [op])[0]
