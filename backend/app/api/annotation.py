"""Second opinions, agreement and adjudication (annotation guideline, section 7)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import DbSession, client_ip, require_roles
from app.models.event import EventEvidence
from app.models.user import Role, User
from app.schemas.annotation import (
    Adjudication,
    AgreementRead,
    Disagreement,
    JudgementCreate,
    JudgementRead,
    QueueItem,
    QueuePage,
)
from app.schemas.event import EventRead, EvidenceRead
from app.schemas.field_report import FieldReportRead
from app.schemas.signal import SignalRead
from app.services import annotation as service

router = APIRouter(prefix="/annotation", tags=["annotation"])

Reviewer = Annotated[User, Depends(require_roles(Role.ANALYST, Role.ADMIN))]


def _evidence_or_422(db, evidence_id) -> EventEvidence:
    item = db.get(EventEvidence, evidence_id)
    if item is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Link not found")
    return item


def _items(link: EventEvidence) -> dict:
    return {
        "event": EventRead.model_validate(link.event),
        "field_report": FieldReportRead.model_validate(link.field_report)
        if link.field_report
        else None,
        "signal": SignalRead.model_validate(link.signal) if link.signal else None,
    }


@router.get("/queue", response_model=QueuePage)
def queue(
    db: DbSession,
    user: Reviewer,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Links waiting for this analyst's independent judgement, oldest first. Labels
    already given are not shown, so the second opinion stays blind."""
    links, total = service.queue(db, user, limit=limit, offset=offset)
    return QueuePage(
        items=[
            QueueItem(evidence_id=link.id, judgements=len(link.judgements), **_items(link))
            for link in links
        ],
        total=total,
    )


@router.post("/judgements", response_model=JudgementRead, status_code=status.HTTP_201_CREATED)
def judge(body: JudgementCreate, request: Request, db: DbSession, user: Reviewer):
    link = _evidence_or_422(db, body.evidence_id)
    try:
        return service.judge(
            db,
            actor=user,
            item=link,
            relation=body.relation,
            conflicts=[str(c) for c in body.conflicts],
            stale=body.stale,
            confidence=body.confidence,
            note=body.note,
            ip_address=client_ip(request),
        )
    except service.InvalidJudgementError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None


@router.get("/agreement", response_model=AgreementRead)
def agreement(db: DbSession, _user: Reviewer):
    """Agreement between annotators on relation labels (κ, α, confusion table)."""
    stats = service.agreement(db)
    return AgreementRead(**stats.__dict__, open_disagreements=len(service.disagreements(db)))


@router.get("/disagreements", response_model=list[Disagreement])
def disagreements(
    db: DbSession,
    _user: Reviewer,
    resolved: Annotated[bool, Query(description="Include ones already resolved")] = False,
):
    return [
        Disagreement(
            evidence_id=link.id,
            working=link.relation,
            judgements=[JudgementRead.model_validate(j) for j in link.judgements],
            gold_relation=link.gold_relation,
            gold_by=link.gold_by,
            gold_at=link.gold_at,
            **_items(link),
        )
        for link in service.disagreements(db, include_resolved=resolved)
    ]


@router.post("/adjudicate", response_model=EvidenceRead)
def adjudicate(body: Adjudication, request: Request, db: DbSession, user: Reviewer):
    """Resolve a disagreement into the gold label (guideline 7.3)."""
    link = _evidence_or_422(db, body.evidence_id)
    try:
        return service.adjudicate(
            db,
            actor=user,
            item=link,
            relation=body.relation,
            conflicts=[str(c) for c in body.conflicts],
            note=body.note,
            ip_address=client_ip(request),
        )
    except service.InvalidJudgementError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
