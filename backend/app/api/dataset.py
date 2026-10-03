"""The CARCUX-BD dataset: what is ready, what needs work, and the export itself."""

import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DbSession, client_ip, require_roles
from app.models.event import Event
from app.models.user import Role, User
from app.services import audit
from app.services import dataset as service

router = APIRouter(prefix="/dataset", tags=["dataset"])

Reviewer = Annotated[User, Depends(require_roles(Role.ANALYST, Role.ADMIN))]
Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]


class ProblemRead(BaseModel):
    kind: str
    message: str
    event_id: str | None
    event_title: str | None = None
    evidence_id: str | None


class DatasetSummary(BaseModel):
    schema_version: str
    guideline_version: str
    counts: dict[str, int]
    events_total: int
    problems_by_kind: dict[str, int]
    problems: list[ProblemRead]


@router.get("/summary", response_model=DatasetSummary)
def summary(db: DbSession, _user: Reviewer):
    """What an export would contain now, and what stops the rest from going in."""
    export = service.build(db)
    titles = dict(db.execute(select(Event.id, Event.title)).all())
    problems = [
        ProblemRead(
            **p.__dict__,
            event_title=titles.get(uuid.UUID(p.event_id)) if p.event_id else None,
        )
        for p in export.problems
    ]
    return DatasetSummary(
        schema_version=service.SCHEMA_VERSION,
        guideline_version=service.GUIDELINE_VERSION,
        counts=export.manifest["counts"],
        events_total=len(titles),
        problems_by_kind=dict(Counter(p.kind for p in export.problems)),
        problems=problems[:200],
    )


@router.get("/export", response_class=Response)
def export(
    request: Request,
    db: DbSession,
    user: Admin,
    include_unlinked: Annotated[
        bool, Query(description="Also every report and signal not linked to an exported event")
    ] = False,
):
    """Download the dataset as a zip of JSON Lines files, with manifest and problems."""
    data = service.build(db, include_unlinked=include_unlinked)
    audit.record(
        db,
        audit.AuditAction.DATASET_EXPORTED,
        actor_id=user.id,
        ip_address=client_ip(request),
        details={"counts": data.manifest["counts"], "include_unlinked": include_unlinked},
    )
    db.commit()
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    return Response(
        service.to_zip(data),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="carcux-bd-{stamp}.zip"',
            "Cache-Control": "no-store",
        },
    )
