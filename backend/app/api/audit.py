"""The audit log, read-only, for admins: who did what, to what, and when."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import DbSession, require_roles
from app.models.audit import AuditLog
from app.models.user import Role, User
from app.schemas.field_report import ReporterRead

router = APIRouter(prefix="/audit", tags=["audit"])

AdminUser = Annotated[User, Depends(require_roles(Role.ADMIN))]


class AuditEntry(BaseModel):
    id: int
    occurred_at: datetime
    action: str
    actor: ReporterRead | None
    target_type: str | None
    target_id: str | None
    ip_address: str | None
    details: dict[str, Any]


class AuditPage(BaseModel):
    items: list[AuditEntry]
    total: int
    limit: int
    offset: int
    actions: list[str]


@router.get("", response_model=AuditPage)
def list_entries(
    db: DbSession,
    _admin: AdminUser,
    action: Annotated[
        str | None,
        Query(max_length=64, description="Exact action, or a prefix ending in '.' (e.g. event.)"),
    ] = None,
    actor_id: uuid.UUID | None = None,
    target_type: Annotated[str | None, Query(max_length=64)] = None,
    target_id: Annotated[str | None, Query(max_length=64)] = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    for name, value in (("since", since), ("until", until)):
        if value is not None and value.tzinfo is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"{name} must include a UTC offset"
            )
    query = select(AuditLog)
    if action:
        query = query.where(
            AuditLog.action.startswith(action, autoescape=True)
            if action.endswith(".")
            else AuditLog.action == action
        )
    if actor_id:
        query = query.where(AuditLog.actor_id == actor_id)
    if target_type:
        query = query.where(AuditLog.target_type == target_type)
    if target_id:
        query = query.where(AuditLog.target_id == target_id)
    if since:
        query = query.where(AuditLog.occurred_at >= since)
    if until:
        query = query.where(AuditLog.occurred_at < until)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(
        select(AuditLog, User)
        .outerjoin(User, User.id == AuditLog.actor_id)
        .where(AuditLog.id.in_(select(query.subquery().c.id)))
        .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    actions = list(db.scalars(select(AuditLog.action).distinct().order_by(AuditLog.action)))
    return AuditPage(
        items=[
            AuditEntry(
                id=e.id,
                occurred_at=e.occurred_at,
                action=e.action,
                actor=ReporterRead.model_validate(u) if u else None,
                target_type=e.target_type,
                target_id=e.target_id,
                ip_address=e.ip_address,
                details=e.details,
            )
            for e, u in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
        actions=actions,
    )
