"""Submitting, listing and verifying field reports."""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.field_report import FieldReport, FieldReportMedia
from app.models.user import Role, User
from app.services import audit, integrity
from app.services.media import CheckedPhoto, file_sha256, resolve, storage_key_for

HASH_VERSION = 1


class ClientIdConflictError(Exception):
    """The same client_report_id was reused for different content."""


@dataclass(frozen=True)
class ReportInput:
    client_report_id: uuid.UUID
    text: str
    event_type: str | None
    place_name: str | None
    latitude: float
    longitude: float
    location_accuracy_m: float | None
    observed_at: datetime


def content_hash(
    *,
    reporter_id: uuid.UUID,
    data: ReportInput,
    photo_sha256s: list[str],
) -> str:
    """SHA-256 over a canonical JSON form of the report and its photos' hashes.

    Canonical: sorted keys, no spaces, UTC times, fixed float precision, photos in
    submission order. Any change to text, place, time, location or a photo changes it.
    """
    canonical = {
        "v": HASH_VERSION,
        "reporter_id": str(reporter_id),
        "client_report_id": str(data.client_report_id),
        "text": data.text,
        "event_type": data.event_type,
        "place_name": data.place_name,
        "latitude": f"{data.latitude:.7f}",
        "longitude": f"{data.longitude:.7f}",
        "location_accuracy_m": None
        if data.location_accuracy_m is None
        else f"{data.location_accuracy_m:.2f}",
        "observed_at": data.observed_at.astimezone(UTC).isoformat(),
        "photos": photo_sha256s,
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _input_from(report: FieldReport) -> ReportInput:
    return ReportInput(
        client_report_id=report.client_report_id,
        text=report.text,
        event_type=report.event_type,
        place_name=report.place_name,
        latitude=report.latitude,
        longitude=report.longitude,
        location_accuracy_m=report.location_accuracy_m,
        observed_at=report.observed_at,
    )


def submit(
    db: Session,
    settings: Settings,
    *,
    reporter: User,
    data: ReportInput,
    photos: list[CheckedPhoto],
    ip_address: str | None,
) -> tuple[FieldReport, bool]:
    """Store a report. Returns (report, created). Retries of the same report are no-ops."""
    digest = content_hash(
        reporter_id=reporter.id, data=data, photo_sha256s=[p.sha256 for p in photos]
    )

    existing = db.scalar(
        select(FieldReport).where(
            FieldReport.reporter_id == reporter.id,
            FieldReport.client_report_id == data.client_report_id,
        )
    )
    if existing is not None:
        if existing.content_hash != digest:
            raise ClientIdConflictError
        return existing, False

    now = datetime.now(UTC)
    flags = integrity.evaluate(
        db,
        reporter_id=reporter.id,
        latitude=data.latitude,
        longitude=data.longitude,
        accuracy_m=data.location_accuracy_m,
        observed_at=data.observed_at,
        now=now,
        photos=photos,
    )

    report = FieldReport(
        id=uuid.uuid4(),
        client_report_id=data.client_report_id,
        reporter_id=reporter.id,
        text=data.text,
        event_type=data.event_type,
        place_name=data.place_name,
        latitude=data.latitude,
        longitude=data.longitude,
        location_accuracy_m=data.location_accuracy_m,
        observed_at=data.observed_at,
        content_hash=digest,
        hash_version=HASH_VERSION,
        integrity_flags=flags,
    )
    db.add(report)

    written: list = []
    try:
        for position, photo in enumerate(photos):
            media_id = uuid.uuid4()
            key = storage_key_for(report.id, media_id, photo.extension)
            path = resolve(settings.media_dir, key)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(photo.data)
            written.append(path)
            db.add(
                FieldReportMedia(
                    id=media_id,
                    report_id=report.id,
                    position=position,
                    content_type=photo.content_type,
                    size_bytes=len(photo.data),
                    width=photo.width,
                    height=photo.height,
                    sha256=photo.sha256,
                    dhash=photo.dhash,
                    storage_key=key,
                )
            )
        audit.record(
            db,
            audit.AuditAction.FIELD_REPORT_SUBMITTED,
            actor_id=reporter.id,
            target_type="field_report",
            target_id=report.id,
            ip_address=ip_address,
            details={
                "client_report_id": str(data.client_report_id),
                "photos": len(photos),
                "flags": [f["code"] for f in flags],
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        for path in written:  # don't leave orphaned files behind
            path.unlink(missing_ok=True)
        raise
    db.refresh(report)
    return report, True


def visible_reports(user: User) -> Select[tuple[FieldReport]]:
    """Field workers see only their own reports; analysts and admins see all."""
    query = select(FieldReport)
    if user.role == Role.FIELD_WORKER:
        query = query.where(FieldReport.reporter_id == user.id)
    return query


def get_visible(db: Session, user: User, report_id: uuid.UUID) -> FieldReport | None:
    return db.scalar(visible_reports(user).where(FieldReport.id == report_id))


def verify(settings: Settings, report: FieldReport) -> list[str]:
    """Recompute everything the stored hash covers. Returns a list of problems (empty = intact)."""
    problems: list[str] = []
    for m in report.media:
        actual = file_sha256(resolve(settings.media_dir, m.storage_key))
        if actual is None:
            problems.append(f"Photo {m.position + 1} file is missing.")
        elif actual != m.sha256:
            problems.append(f"Photo {m.position + 1} file has changed since submission.")

    expected = content_hash(
        reporter_id=report.reporter_id,
        data=_input_from(report),
        photo_sha256s=[m.sha256 for m in report.media],
    )
    if expected != report.content_hash:
        problems.append("Report content has changed since submission.")
    return problems
