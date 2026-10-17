"""Integrity checks on field reports, and a risk score per field-worker account.

Flags mark a report for human review; they never block it. The rules here read the
database; `location_text_mismatch`, `copied_text` and the account score come from
ai/integrity (copied into app/integrity). Thresholds are deliberately conservative.
"""

import math
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrity import account, checks
from app.models.field_report import FieldReport, FieldReportMedia
from app.models.signal import Signal
from app.models.user import Role, User
from app.services.media import CheckedPhoto, hamming

MAX_PLAUSIBLE_SPEED_KMH = 150.0  # faster than this between two reports is suspicious
MIN_DISTANCE_FOR_TRAVEL_KM = 2.0  # ignore GPS jitter
FUTURE_TOLERANCE = timedelta(minutes=5)  # phone clocks drift
OLD_OBSERVATION = timedelta(hours=24)  # offline queues are fine; a day is worth a look
BURST_WINDOW = timedelta(minutes=10)
BURST_COUNT = 10
POOR_ACCURACY_M = 1000.0
NEAR_DUPLICATE_BITS = 6  # dhash distance treated as "same photo"
COPY_LOOKBACK = timedelta(days=7)  # public posts and reports to compare a report's words with
COPY_LIMIT = 2000  # newest of each; enough at pilot scale
ACCOUNT_LOOKBACK = timedelta(days=30)  # history the account score compares the last day with


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def evaluate(
    db: Session,
    *,
    reporter_id: uuid.UUID,
    text: str,
    latitude: float,
    longitude: float,
    accuracy_m: float | None,
    observed_at: datetime,
    now: datetime,
    photos: list[CheckedPhoto],
) -> list[dict]:
    flags: list[dict] = []

    if observed_at > now + FUTURE_TOLERANCE:
        flags.append({"code": "observed_in_future", "detail": "Observation time is in the future."})
    elif now - observed_at > OLD_OBSERVATION:
        hours = int((now - observed_at).total_seconds() // 3600)
        flags.append(
            {"code": "old_observation", "detail": f"Observed {hours} h before submission."}
        )

    if accuracy_m is not None and accuracy_m > POOR_ACCURACY_M:
        flags.append(
            {"code": "poor_location_accuracy", "detail": f"GPS accuracy {accuracy_m:.0f} m."}
        )

    # Impossible travel: compare with this reporter's observation closest in time.
    previous = db.scalars(
        select(FieldReport)
        .where(FieldReport.reporter_id == reporter_id)
        .order_by(func.abs(func.extract("epoch", FieldReport.observed_at - observed_at)))
        .limit(1)
    ).first()
    if previous is not None:
        km = haversine_km(previous.latitude, previous.longitude, latitude, longitude)
        hours = abs((observed_at - previous.observed_at).total_seconds()) / 3600
        if km > MIN_DISTANCE_FOR_TRAVEL_KM:
            speed = km / hours if hours > 0 else math.inf
            if speed > MAX_PLAUSIBLE_SPEED_KMH:
                shown = "instantly" if math.isinf(speed) else f"at {speed:.0f} km/h"
                flags.append(
                    {
                        "code": "impossible_travel",
                        "detail": f"{km:.1f} km from report {previous.id} {shown}.",
                    }
                )

    recent = db.scalar(
        select(func.count())
        .select_from(FieldReport)
        .where(FieldReport.reporter_id == reporter_id, FieldReport.received_at > now - BURST_WINDOW)
    )
    if recent >= BURST_COUNT:
        flags.append({"code": "submission_burst", "detail": f"{recent + 1} reports in 10 minutes."})

    # Reused photos: exact copies or near-duplicates of any earlier report's photo.
    # Linear scan is fine at pilot scale; replace with an index when volume grows.
    if photos:
        known = db.execute(
            select(FieldReportMedia.report_id, FieldReportMedia.sha256, FieldReportMedia.dhash)
        ).all()
        for i, photo in enumerate(photos, start=1):
            for report_id, sha, dh in known:
                if sha == photo.sha256 or hamming(dh, photo.dhash) <= NEAR_DUPLICATE_BITS:
                    kind = "identical to" if sha == photo.sha256 else "near-identical to"
                    flags.append(
                        {
                            "code": "photo_reused",
                            "detail": f"Photo {i} is {kind} a photo in report {report_id}.",
                        }
                    )
                    break

    # From ai/integrity: the text against the GPS, and words copied from elsewhere.
    this = checks.Report(
        "new", str(reporter_id), text, latitude, longitude, observed_at, now, accuracy_m
    )
    found = checks.location_text_mismatch(this) + checks.copied_text(
        this, _texts_to_compare(db, now)
    )
    flags += [{"code": f.code, "detail": f.detail} for f in found]
    return flags


def _texts_to_compare(db: Session, now: datetime) -> list[checks.Text]:
    since = now - COPY_LOOKBACK
    posts = db.execute(
        select(Signal.id, Signal.title, Signal.text)
        .where(Signal.collected_at > since)
        .order_by(Signal.collected_at.desc())
        .limit(COPY_LIMIT)
    ).all()
    reports = db.execute(
        select(FieldReport.id, FieldReport.text, FieldReport.reporter_id)
        .where(FieldReport.received_at > since)
        .order_by(FieldReport.received_at.desc())
        .limit(COPY_LIMIT)
    ).all()
    texts = [
        checks.Text(str(i), f"{title} {body or ''}".strip(), "public post")
        for i, title, body in posts
    ]
    texts += [checks.Text(str(i), t, "report", str(who)) for i, t, who in reports]
    return texts


def _as_check(r: FieldReport) -> checks.Report:
    return checks.Report(
        str(r.id), str(r.reporter_id), r.text, r.latitude, r.longitude,
        r.observed_at, r.received_at, r.location_accuracy_m,
    )  # fmt: skip


def account_risks(db: Session, now: datetime) -> list[tuple[User, account.AccountRisk]]:
    """Each active field worker's risk now, highest first. Account-level only, for
    CARCUX's own field workers; it marks an account for a conversation, never blocks it."""
    workers = db.scalars(
        select(User).where(User.role == Role.FIELD_WORKER, User.is_active.is_(True))
    ).all()
    if not workers:
        return []
    reports = db.scalars(
        select(FieldReport).where(
            FieldReport.reporter_id.in_([w.id for w in workers]),
            FieldReport.received_at > now - ACCOUNT_LOOKBACK,
            FieldReport.received_at <= now,
        )
    ).all()
    as_checks = [_as_check(r) for r in reports]
    flags = {
        str(r.id): [checks.Flag(f["code"], f.get("detail", "")) for f in r.integrity_flags or []]
        for r in reports
    }
    out = [(w, account.score(str(w.id), as_checks, flags, now)) for w in workers]
    return sorted(out, key=lambda x: (-x[1].score, x[0].full_name))
