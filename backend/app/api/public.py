"""The public site's API: open to everyone for reading; a verified public account to
like, comment and report. Staff tokens are not accepted here, nor public tokens on
staff endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.api.deps import AppSettings, DbSession
from app.core.security import InvalidTokenError, create_public_token, decode_public_token
from app.models.official import OfficialPage, PageStatus
from app.models.public import AccountStatus, IncidentOpinion, PublicAccount, StatementComment
from app.models.statement import Statement
from app.schemas.public import (
    CommentCreate,
    Incident,
    Login,
    Me,
    OpinionCreate,
    PasswordConfirm,
    PublicComment,
    PublicOpinion,
    PublicPage,
    PublicPost,
    PublicPostDetail,
    PublicToken,
    ReportCreate,
    Signup,
    VerifyEmail,
)
from app.schemas.statement import EventLite, PageLite
from app.services import public as service
from app.services.statements import superseded_by

router = APIRouter(prefix="/public", tags=["public"])
_bearer = HTTPBearer(auto_error=False)


def optional_account(
    db: DbSession,
    settings: AppSettings,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> PublicAccount | None:
    if credentials is None:
        return None
    try:
        claims = decode_public_token(settings, credentials.credentials)
    except InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in again") from None
    account = db.get(PublicAccount, claims.account_id)
    if (
        account is None
        or account.status != AccountStatus.ACTIVE
        or account.token_version != claims.token_version
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in again")
    return account


Viewer = Annotated[PublicAccount | None, Depends(optional_account)]


def _required(account: PublicAccount | None) -> PublicAccount:
    if account is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to take part")
    return account


def _rule(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


def _posts(db, rows: list[Statement], account) -> list[PublicPost]:
    ids = [s.id for s in rows]
    likes, comments = service.counts(db, ids)
    mine, later = service.liked(db, account, ids), superseded_by(db, ids)
    return [
        PublicPost(
            id=s.id,
            page=PageLite.model_validate(s.page),
            event=EventLite.model_validate(s.event),
            finding=s.finding,
            title=s.title,
            body=s.body,
            published_at=s.published_at,
            supersedes_id=s.supersedes_id,
            superseded_by_id=later.get(s.id),
            likes=likes.get(s.id, 0),
            comments=comments.get(s.id, 0),
            liked=s.id in mine,
        )  # fmt: skip
        for s in rows
    ]


def _visible():
    return select(Statement).join(OfficialPage).where(OfficialPage.status == PageStatus.VERIFIED)


def _post_or_404(db, statement_id: uuid.UUID) -> Statement:
    st = service.visible_statement(db, statement_id)
    if st is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    return st


# --- Reading ------------------------------------------------------------------------------


@router.get("/posts", response_model=list[PublicPost])
def feed(
    db: DbSession,
    account: Viewer,
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
):
    """Official posts from verified pages, newest first."""
    rows = db.scalars(
        _visible().order_by(Statement.published_at.desc()).limit(limit).offset(offset)
    ).all()
    return _posts(db, list(rows), account)


@router.get("/posts/{statement_id}", response_model=PublicPostDetail)
def post(statement_id: uuid.UUID, db: DbSession, account: Viewer):
    st = _post_or_404(db, statement_id)
    comments = db.scalars(
        select(StatementComment)
        .where(StatementComment.statement_id == st.id, StatementComment.hidden_at.is_(None))
        .order_by(StatementComment.created_at)
    ).all()
    base = _posts(db, [st], account)[0]
    return PublicPostDetail(
        **base.model_dump(),
        comment_list=[
            PublicComment(
                id=c.id,
                author=c.account.display_name,
                body=c.body,
                created_at=c.created_at,
                mine=account is not None and c.account_id == account.id,
            )  # fmt: skip
            for c in comments
        ],
    )


@router.get("/pages/{slug}", response_model=PublicPage)
def page(slug: str, db: DbSession, account: Viewer):
    p = db.scalar(select(OfficialPage).where(OfficialPage.slug == slug.lower()))
    if p is None or p.status != PageStatus.VERIFIED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Page not found")
    rows = db.scalars(
        _visible().where(Statement.page_id == p.id).order_by(Statement.published_at.desc())
    ).all()
    return PublicPage(
        page=PageLite.model_validate(p), description=p.description, website=p.website,
        verified_at=p.verified_at, posts=_posts(db, list(rows), account),
    )  # fmt: skip


@router.get("/incidents/{event_id}", response_model=Incident)
def incident(event_id: uuid.UUID, db: DbSession, account: Viewer):
    """An incident is public once a verified page has posted about it: its official posts,
    and what people say about it (newest first)."""
    event = service.public_incident(db, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")
    rows = db.scalars(
        _visible().where(Statement.event_id == event_id).order_by(Statement.published_at.desc())
    ).all()
    opinions = db.scalars(
        select(IncidentOpinion)
        .where(IncidentOpinion.event_id == event_id, IncidentOpinion.hidden_at.is_(None))
        .order_by(IncidentOpinion.created_at.desc())
        .limit(200)
    ).all()
    return Incident(
        event=EventLite.model_validate(event),
        posts=_posts(db, list(rows), account),
        opinions=[_opinion(o, account) for o in opinions],
    )


def _opinion(o: IncidentOpinion, account) -> PublicOpinion:
    return PublicOpinion(
        id=o.id, author=o.account.display_name, body=o.body, created_at=o.created_at,
        mine=account is not None and o.account_id == account.id,
    )  # fmt: skip


# --- Accounts -----------------------------------------------------------------------------


@router.post("/auth/signup", status_code=status.HTTP_202_ACCEPTED)
def signup(body: Signup, db: DbSession, settings: AppSettings) -> dict:
    try:
        service.signup(
            db, settings, email=body.email, display_name=body.display_name, password=body.password
        )
    except ValueError as exc:
        raise _rule(exc) from None
    db.commit()
    return {"detail": "Check your email for a link to confirm your account."}


@router.post("/auth/verify", response_model=PublicToken)
def verify(body: VerifyEmail, db: DbSession, settings: AppSettings):
    try:
        account = service.verify_email(db, body.token)
    except ValueError as exc:
        raise _rule(exc) from None
    db.commit()
    token, expires = create_public_token(settings, account.id, account.token_version)
    return PublicToken(access_token=token, expires_in=expires)


@router.post("/auth/login", response_model=PublicToken)
def login(body: Login, db: DbSession, settings: AppSettings):
    try:
        account = service.authenticate(db, body.email, body.password)
    except ValueError as exc:
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from None
    db.commit()
    token, expires = create_public_token(settings, account.id, account.token_version)
    return PublicToken(access_token=token, expires_in=expires)


@router.get("/auth/me", response_model=Me)
def me(account: Viewer):
    a = _required(account)
    return Me(id=a.id, display_name=a.display_name, email=a.email)


@router.post("/auth/delete", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(body: PasswordConfirm, db: DbSession, account: Viewer):
    """Delete the account with its likes, comments and reports."""
    try:
        service.delete_account(db, _required(account), body.password)
    except ValueError as exc:
        raise _rule(exc) from None
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Taking part --------------------------------------------------------------------------


@router.put("/posts/{statement_id}/like", status_code=status.HTTP_204_NO_CONTENT)
def like(statement_id: uuid.UUID, db: DbSession, account: Viewer):
    service.set_like(db, _required(account), _post_or_404(db, statement_id), True)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/posts/{statement_id}/like", status_code=status.HTTP_204_NO_CONTENT)
def unlike(statement_id: uuid.UUID, db: DbSession, account: Viewer):
    service.set_like(db, _required(account), _post_or_404(db, statement_id), False)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/posts/{statement_id}/comments",
    response_model=PublicComment,
    status_code=status.HTTP_201_CREATED,
)
def add_comment(statement_id: uuid.UUID, body: CommentCreate, db: DbSession, account: Viewer):
    a = _required(account)
    try:
        c = service.comment(db, a, _post_or_404(db, statement_id), body.body)
    except ValueError as exc:
        raise _rule(exc) from None
    db.commit()
    return PublicComment(
        id=c.id, author=a.display_name, body=c.body, created_at=c.created_at, mine=True
    )


def _comment_or_404(db, comment_id: uuid.UUID) -> StatementComment:
    c = db.get(StatementComment, comment_id)
    if c is None or c.hidden_at is not None or not service.visible_statement(db, c.statement_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment not found")
    return c


@router.post("/comments/{comment_id}/report", status_code=status.HTTP_204_NO_CONTENT)
def report_comment(comment_id: uuid.UUID, body: ReportCreate, db: DbSession, account: Viewer):
    try:
        service.report(db, _required(account), _comment_or_404(db, comment_id), body.reason)
    except ValueError as exc:
        raise _rule(exc) from None
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(comment_id: uuid.UUID, db: DbSession, account: Viewer):
    a = _required(account)
    c = db.get(StatementComment, comment_id)
    if c is None or c.account_id != a.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment not found")
    db.delete(c)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Opinions on incidents ----------------------------------------------------------------


@router.post(
    "/incidents/{event_id}/opinions",
    response_model=PublicOpinion,
    status_code=status.HTTP_201_CREATED,
)
def add_opinion(
    event_id: uuid.UUID, body: OpinionCreate, db: DbSession, settings: AppSettings,
    account: Viewer,
):  # fmt: skip
    a = _required(account)
    event = service.public_incident(db, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")
    try:
        op = service.opinion(db, settings, a, event, body.body)
    except ValueError as exc:
        raise _rule(exc) from None
    db.commit()
    return _opinion(op, a)


def _opinion_or_404(db, opinion_id: uuid.UUID) -> IncidentOpinion:
    op = db.get(IncidentOpinion, opinion_id)
    if op is None or op.hidden_at is not None or service.public_incident(db, op.event_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Opinion not found")
    return op


@router.post("/opinions/{opinion_id}/report", status_code=status.HTTP_204_NO_CONTENT)
def report_opinion(opinion_id: uuid.UUID, body: ReportCreate, db: DbSession, account: Viewer):
    try:
        service.report_opinion(db, _required(account), _opinion_or_404(db, opinion_id), body.reason)
    except ValueError as exc:
        raise _rule(exc) from None
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/opinions/{opinion_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_opinion(opinion_id: uuid.UUID, db: DbSession, account: Viewer):
    a = _required(account)
    op = db.get(IncidentOpinion, opinion_id)
    if op is None or op.account_id != a.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Opinion not found")
    service.delete_opinion(db, a, op)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
