"""One call for the console's status bar: what needs attention right now."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models.event import Event, EventStatus, Priority
from app.models.field_report import FieldReport, ReportStatus
from app.models.user import Role
from app.services.field_reports import visible_reports

router = APIRouter(tags=["overview"])

OPEN = (EventStatus.ACTIVE, EventStatus.MONITORING)
REVIEWERS = (Role.ANALYST, Role.ADMIN)


class Overview(BaseModel):
    as_of: datetime
    open_events: int
    open_by_priority: dict[str, int]
    reports_24h: int
    # Reviewers only (null for others): flags and the review backlog.
    flagged_24h: int | None
    unreviewed_reports: int | None


@router.get("/overview", response_model=Overview)
def overview(db: DbSession, user: CurrentUser):
    now = datetime.now(UTC)
    by_priority = dict(
        db.execute(
            select(Event.priority, func.count())
            .where(Event.status.in_(OPEN))
            .group_by(Event.priority)
        ).all()
    )
    counts = {p.value: by_priority.get(p, 0) for p in Priority}

    recent = visible_reports(user).where(FieldReport.observed_at >= now - timedelta(hours=24))
    reports_24h = db.scalar(select(func.count()).select_from(recent.subquery())) or 0

    flagged = unreviewed = None
    if user.role in REVIEWERS:
        flagged = (
            db.scalar(
                select(func.count()).select_from(
                    recent.where(
                        func.jsonb_array_length(FieldReport.integrity_flags) > 0
                    ).subquery()
                )
            )
            or 0
        )
        unreviewed = (
            db.scalar(
                select(func.count())
                .select_from(FieldReport)
                .where(FieldReport.status == ReportStatus.SUBMITTED)
            )
            or 0
        )

    return Overview(
        as_of=now,
        open_events=sum(counts.values()),
        open_by_priority=counts,
        reports_24h=reports_24h,
        flagged_24h=flagged,
        unreviewed_reports=unreviewed,
    )
