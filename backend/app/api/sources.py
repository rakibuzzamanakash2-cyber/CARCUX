"""Sources of public signals. Analysts and admins see them; admins add news feeds,
switch sources on and off, and read one immediately."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select

from app.api.deps import AppSettings, DbSession, client_ip, require_roles
from app.ingest import runner
from app.models.signal import Adapter, IngestRun, Source
from app.models.user import Role, User
from app.schemas.signal import (
    BackfillRequest,
    IngestRunRead,
    SourceCreate,
    SourceRead,
    SourceUpdate,
)
from app.services import audit
from app.services import signals as service

router = APIRouter(prefix="/sources", tags=["signals"])

Reviewer = Annotated[User, Depends(require_roles(Role.ANALYST, Role.ADMIN))]
Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]


def _source_or_404(db, source_id: uuid.UUID) -> Source:
    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found")
    return source


def _read(source: Source, counts: dict) -> SourceRead:
    total, recent = counts.get(source.id, (0, 0))
    return SourceRead.model_validate(source).model_copy(
        update={"signal_count": total, "signals_24h": recent}
    )


@router.get("", response_model=list[SourceRead])
def list_sources(db: DbSession, _user: Reviewer):
    counts = service.source_counts(db, datetime.now(UTC) - timedelta(hours=24))
    sources = db.scalars(select(Source).order_by(Source.adapter, Source.name)).all()
    return [_read(s, counts) for s in sources]


@router.post("", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
def add_feed(body: SourceCreate, request: Request, db: DbSession, user: Admin):
    """Add a news feed (RSS or Atom)."""
    source = service.add_feed(db, actor=user, data=body.model_dump(), ip_address=client_ip(request))
    return _read(source, {})


@router.patch("/{source_id}", response_model=SourceRead)
def update_source(
    source_id: uuid.UUID, body: SourceUpdate, request: Request, db: DbSession, user: Admin
):
    source = _source_or_404(db, source_id)
    changes = body.model_dump(exclude_unset=True)
    if source.adapter == Adapter.MANUAL and ({"url", "interval_minutes"} & changes.keys()):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Bulletins from this source are entered by hand; it has no address to read",
        )
    source = service.update_source(
        db, actor=user, source=source, changes=changes, ip_address=client_ip(request)
    )
    counts = service.source_counts(db, datetime.now(UTC) - timedelta(hours=24))
    return _read(source, counts)


@router.post("/{source_id}/fetch", response_model=IngestRunRead)
def fetch_now(
    source_id: uuid.UUID, request: Request, db: DbSession, settings: AppSettings, user: Admin
):
    """Read the source now. Problems with the source are reported in the run, not as errors."""
    source = _source_or_404(db, source_id)
    audit.record(
        db,
        audit.AuditAction.SOURCE_FETCHED,
        actor_id=user.id,
        target_type="source",
        target_id=source.id,
        ip_address=client_ip(request),
        details={"key": source.key},
    )
    try:
        run = runner.run_source(db, source, settings, actor=user)
    except runner.NotReadableError:
        db.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "This source is entered by hand"
        ) from None
    except runner.AlreadyRunningError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This source is being read already") from None
    return run


@router.post("/{source_id}/backfill", response_model=IngestRunRead)
def backfill(
    source_id: uuid.UUID,
    body: BackfillRequest,
    request: Request,
    db: DbSession,
    settings: AppSettings,
    user: Admin,
):
    """Read a past period from the source's archive (GDACS, ReliefWeb)."""
    source = _source_or_404(db, source_id)
    audit.record(
        db,
        audit.AuditAction.SOURCE_BACKFILLED,
        actor_id=user.id,
        target_type="source",
        target_id=source.id,
        ip_address=client_ip(request),
        details={"key": source.key, "start": body.start.isoformat(), "end": body.end.isoformat()},
    )
    try:
        return runner.backfill(db, source, settings, body.start, body.end, actor=user)
    except runner.NoArchiveError:
        db.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"{source.name} has no archive to search; import a list of items instead",
        ) from None
    except runner.BadWindowError:
        db.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Choose a period of at most a year that has started, with the end after the start",
        ) from None
    except runner.AlreadyRunningError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This source is being read already") from None


@router.get("/{source_id}/runs", response_model=list[IngestRunRead])
def runs(
    source_id: uuid.UUID,
    db: DbSession,
    _user: Reviewer,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    _source_or_404(db, source_id)
    return db.scalars(
        select(IngestRun)
        .where(IngestRun.source_id == source_id)
        .order_by(IngestRun.started_at.desc())
        .limit(limit)
    ).all()
