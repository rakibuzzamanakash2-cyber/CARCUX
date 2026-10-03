"""Field reports: submit (field workers), read (field workers: own; analysts, admins: all)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import func, or_, select

from app.api.deps import AppSettings, DbSession, client_ip, require_roles
from app.core.event_types import BD_LAT, BD_LON, EVENT_TYPE_FAMILY, EVENT_TYPES
from app.models.field_report import FieldReport, FieldReportMedia, ReportStatus
from app.models.user import Role, User
from app.schemas.event import CandidateEvent, EventRead, ReportLink
from app.schemas.field_report import (
    FieldReportPage,
    FieldReportRead,
    ReviewDecision,
    VerifyResult,
)
from app.services import audit
from app.services import events as event_service
from app.services import field_reports as service
from app.services.media import InvalidMediaError, check_photo, resolve

router = APIRouter(prefix="/field-reports", tags=["field reports"])

Submitter = Annotated[User, Depends(require_roles(Role.FIELD_WORKER, Role.ADMIN))]
Reader = Annotated[User, Depends(require_roles(Role.FIELD_WORKER, Role.ANALYST, Role.ADMIN))]
Reviewer = Annotated[User, Depends(require_roles(Role.ANALYST, Role.ADMIN))]

_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Field report not found")


def _unprocessable(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


@router.post(
    "",
    response_model=FieldReportRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "Same report submitted again (offline retry); nothing changed"}
    },
)
async def submit_report(
    request: Request,
    db: DbSession,
    settings: AppSettings,
    reporter: Submitter,
    client_report_id: Annotated[
        uuid.UUID, Form(description="Generated on the device; makes retries safe")
    ],
    text: Annotated[str, Form(min_length=1, max_length=4000)],
    latitude: Annotated[float, Form(ge=BD_LAT[0], le=BD_LAT[1])],
    longitude: Annotated[float, Form(ge=BD_LON[0], le=BD_LON[1])],
    observed_at: Annotated[
        datetime, Form(description="When the situation was seen, with UTC offset")
    ],
    event_type: Annotated[str | None, Form()] = None,
    place_name: Annotated[str | None, Form(max_length=200)] = None,
    location_accuracy_m: Annotated[float | None, Form(gt=0, le=100_000)] = None,
    photos: Annotated[list[UploadFile], File()] = [],  # noqa: B006 (FastAPI form default)
):
    if observed_at.tzinfo is None:
        raise _unprocessable("observed_at must include a UTC offset, e.g. +06:00")
    if event_type is not None and event_type not in EVENT_TYPES:
        raise _unprocessable(f"Unknown event_type '{event_type}'")
    if len(photos) > settings.max_photos_per_report:
        raise _unprocessable(f"At most {settings.max_photos_per_report} photos per report")

    checked = []
    for i, upload in enumerate(photos, start=1):
        # Read at most one byte past the limit, so oversized files are refused cheaply.
        data = await upload.read(settings.max_photo_bytes + 1)
        try:
            checked.append(check_photo(data, settings.max_photo_bytes, f"Photo {i}"))
        except InvalidMediaError as exc:
            raise _unprocessable(str(exc)) from None

    data = service.ReportInput(
        client_report_id=client_report_id,
        text=text.strip(),
        event_type=event_type,
        place_name=place_name.strip() if place_name else None,
        latitude=latitude,
        longitude=longitude,
        location_accuracy_m=location_accuracy_m,
        observed_at=observed_at,
    )
    try:
        report, created = service.submit(
            db,
            settings,
            reporter=reporter,
            data=data,
            photos=checked,
            ip_address=client_ip(request),
        )
    except service.ClientIdConflictError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "client_report_id was already used for a different report",
        ) from None

    body = FieldReportRead.model_validate(report).model_dump(mode="json")
    return JSONResponse(
        body, status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK
    )


@router.get("", response_model=FieldReportPage)
def list_reports(
    db: DbSession,
    user: Reader,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    flagged: Annotated[bool | None, Query(description="Only reports with integrity flags")] = None,
    since: Annotated[
        datetime | None, Query(description="Only reports observed at or after this time")
    ] = None,
    q: Annotated[
        str | None, Query(max_length=100, description="Words in the text or place")
    ] = None,
    status_: Annotated[
        list[ReportStatus] | None,
        Query(alias="status", description="Repeat to include several; default all"),
    ] = None,
    order: Annotated[
        Literal["newest", "oldest"], Query(description="By arrival; oldest first for a queue")
    ] = "newest",
):
    query = service.visible_reports(user)
    if since is not None:
        if since.tzinfo is None:
            raise _unprocessable("since must include a UTC offset, e.g. +06:00")
        query = query.where(FieldReport.observed_at >= since)
    if q and q.strip():
        pattern = f"%{event_service.escape_like(q.strip())}%"
        query = query.where(
            or_(
                FieldReport.text.ilike(pattern, escape="\\"),
                FieldReport.place_name.ilike(pattern, escape="\\"),
            )
        )
    if flagged is True:
        query = query.where(func.jsonb_array_length(FieldReport.integrity_flags) > 0)
    elif flagged is False:
        query = query.where(func.jsonb_array_length(FieldReport.integrity_flags) == 0)

    if status_:
        query = query.where(FieldReport.status.in_(status_))

    total = db.scalar(select(func.count()).select_from(query.subquery()))
    arrival = FieldReport.received_at.asc() if order == "oldest" else FieldReport.received_at.desc()
    items = db.scalars(query.order_by(arrival, FieldReport.id).limit(limit).offset(offset)).all()
    return FieldReportPage(
        items=[FieldReportRead.model_validate(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{report_id}", response_model=FieldReportRead)
def get_report(report_id: uuid.UUID, db: DbSession, user: Reader):
    # Someone else's report looks exactly like a missing one: no existence leak.
    report = service.get_visible(db, user, report_id)
    if report is None:
        raise _NOT_FOUND
    return report


@router.get("/{report_id}/media/{media_id}")
def get_media(
    report_id: uuid.UUID, media_id: uuid.UUID, db: DbSession, settings: AppSettings, user: Reader
):
    report = service.get_visible(db, user, report_id)
    media = db.get(FieldReportMedia, media_id) if report else None
    if report is None or media is None or media.report_id != report.id:
        raise _NOT_FOUND
    path = resolve(settings.media_dir, media.storage_key)
    if not path.is_file():
        raise _NOT_FOUND
    return FileResponse(
        path,
        media_type=media.content_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )


@router.get("/{report_id}/verify", response_model=VerifyResult)
def verify_report(
    report_id: uuid.UUID, request: Request, db: DbSession, settings: AppSettings, user: Reviewer
):
    report = db.get(FieldReport, report_id)
    if report is None:
        raise _NOT_FOUND
    problems = service.verify(settings, report)
    audit.record(
        db,
        audit.AuditAction.FIELD_REPORT_VERIFIED,
        actor_id=user.id,
        target_type="field_report",
        target_id=report.id,
        ip_address=client_ip(request),
        details={"intact": not problems, "problems": problems},
    )
    db.commit()
    return VerifyResult(
        report_id=report.id,
        intact=not problems,
        problems=problems,
        content_hash=report.content_hash,
    )


@router.get("/{report_id}/events", response_model=list[ReportLink])
def report_events(report_id: uuid.UUID, db: DbSession, _user: Reviewer):
    """Events this report is evidence for, and how."""
    if db.get(FieldReport, report_id) is None:
        raise _NOT_FOUND
    return [
        ReportLink(
            evidence_id=item.id, relation=item.relation, event=EventRead.model_validate(item.event)
        )
        for item in event_service.links_for_report(db, report_id)
    ]


@router.get("/{report_id}/candidate-events", response_model=list[CandidateEvent])
def candidate_events(report_id: uuid.UUID, db: DbSession, _user: Reviewer):
    """Events within 5 km and 48 h that this report may belong to: suggestions only."""
    report = db.get(FieldReport, report_id)
    if report is None:
        raise _NOT_FOUND
    family = EVENT_TYPE_FAMILY.get(report.event_type or "")
    return [
        CandidateEvent(
            event=EventRead.model_validate(event),
            distance_km=m.distance_km,
            hours_apart=m.hours_apart,
            same_type=event.event_type == report.event_type,
            same_family=family is not None and event.family == family,
        )
        for event, m in event_service.candidate_events(db, report)
    ]


@router.post("/{report_id}/review", response_model=FieldReportRead)
def review_report(
    report_id: uuid.UUID, body: ReviewDecision, request: Request, db: DbSession, user: Reviewer
):
    """Triage: mark a report reviewed, dismiss it with a reason, or put it back as new."""
    report = db.get(FieldReport, report_id)
    if report is None:
        raise _NOT_FOUND
    before = report.status
    report.status = body.status
    report.review_note = body.note
    if body.status == ReportStatus.SUBMITTED:
        report.reviewed_by_id = None
        report.reviewed_at = None
    else:
        report.reviewed_by_id = user.id
        report.reviewed_at = datetime.now(UTC)
    audit.record(
        db,
        audit.AuditAction.FIELD_REPORT_REVIEWED,
        actor_id=user.id,
        target_type="field_report",
        target_id=report.id,
        ip_address=client_ip(request),
        details={"from": before.value, "to": body.status.value, "note": body.note},
    )
    db.commit()
    db.refresh(report)
    return report
