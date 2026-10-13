"""Public signals: listing, entering bulletins by hand, and triage."""

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.event_types import EVENT_TYPE_FAMILY
from app.ingest.places import PRECISION_M, gazetteer
from app.models.signal import (
    Adapter,
    ContentPolicy,
    Signal,
    SignalStatus,
    Source,
    SourceType,
)
from app.models.user import User
from app.services import audit
from app.services.events import escape_like


class UnknownDistrictError(Exception):
    pass


class NotManualSourceError(Exception):
    """Bulletins can only be entered for sources that are entered by hand."""


def list_signals(
    db: Session,
    *,
    limit: int,
    offset: int,
    source_ids: list[uuid.UUID] | None = None,
    statuses: list[SignalStatus] | None = None,
    family: str | None = None,
    event_type: str | None = None,
    search: str | None = None,
    since: datetime | None = None,
    located: bool | None = None,
    order: str = "newest",
) -> tuple[list[Signal], int]:
    query = select(Signal)
    if source_ids:
        query = query.where(Signal.source_id.in_(source_ids))
    if statuses:
        query = query.where(Signal.status.in_(statuses))
    if family:
        query = query.where(Signal.family == family)
    if event_type:
        query = query.where(Signal.event_type == event_type)
    if since is not None:
        query = query.where(Signal.published_at >= since)
    if located is True:
        query = query.where(Signal.latitude.is_not(None))
    elif located is False:
        query = query.where(Signal.latitude.is_(None))
    if search:
        pattern = f"%{escape_like(search)}%"
        query = query.where(
            or_(
                Signal.title.ilike(pattern, escape="\\"),
                Signal.text.ilike(pattern, escape="\\"),
                Signal.place_name.ilike(pattern, escape="\\"),
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    when = Signal.published_at.asc() if order == "oldest" else Signal.published_at.desc()
    items = db.scalars(query.order_by(when, Signal.id).limit(limit).offset(offset)).all()
    return list(items), total


def _district(name: str) -> dict:
    wanted = name.casefold()
    for d in gazetteer()["districts"]:
        if d["name"].casefold() == wanted or wanted in (a.casefold() for a in d["aliases"]):
            return d
    raise UnknownDistrictError(name)


def enter_bulletin(
    db: Session, *, actor: User, source: Source, data: dict[str, Any], ip_address: str | None
) -> Signal:
    """A bulletin typed or pasted by an analyst, e.g. a BMD special weather bulletin."""
    if source.adapter != Adapter.MANUAL:
        raise NotManualSourceError
    district = _district(data["district"]) if data.get("district") else None
    if data.get("latitude") is not None:
        lat, lon = data["latitude"], data["longitude"]
        precision = 1_000.0
    else:
        lat, lon = district["lat"], district["lon"]
        precision = float(PRECISION_M["district"])
    place = data.get("place_name") or (district["name"] if district else None)
    signal = Signal(
        id=uuid.uuid4(),
        source_id=source.id,
        external_id=f"manual:{uuid.uuid4()}",
        title=data["title"],
        text=data.get("text"),
        # Typed in by an analyst from an official bulletin; kept in full for the record.
        content_policy=ContentPolicy.FULL,
        url=data.get("url"),
        language=data.get("language", "en"),
        event_type=data["event_type"],
        family=EVENT_TYPE_FAMILY[data["event_type"]],
        severity=data.get("severity"),
        place_name=place,
        district=district["name"] if district else None,
        latitude=lat,
        longitude=lon,
        precision_m=precision,
        published_at=data["published_at"],
        valid_until=data.get("valid_until"),
        extraction={"method": "entered by hand"},
        content_hash="",
        entered_by_id=actor.id,
    )
    db.add(signal)
    db.flush()
    audit.record(
        db,
        audit.AuditAction.SIGNAL_ENTERED,
        actor_id=actor.id,
        target_type="signal",
        target_id=signal.id,
        ip_address=ip_address,
        details={"source": source.key, "title": signal.title, "event_type": signal.event_type},
    )
    db.commit()
    db.refresh(signal)
    return signal


def review(
    db: Session,
    *,
    actor: User,
    signal: Signal,
    status: SignalStatus,
    note: str | None,
    ip_address: str | None,
) -> Signal:
    before = signal.status
    signal.status = status
    signal.review_note = note
    if status == SignalStatus.NEW:
        signal.reviewed_by_id = None
        signal.reviewed_at = None
    else:
        signal.reviewed_by_id = actor.id
        signal.reviewed_at = datetime.now(UTC)
    audit.record(
        db,
        audit.AuditAction.SIGNAL_REVIEWED,
        actor_id=actor.id,
        target_type="signal",
        target_id=signal.id,
        ip_address=ip_address,
        details={"from": before.value, "to": status.value, "note": note},
    )
    db.commit()
    db.refresh(signal)
    return signal


def source_counts(db: Session, since: datetime) -> dict[uuid.UUID, tuple[int, int]]:
    """Per source: (all signals, signals published since `since`)."""
    rows = db.execute(
        select(
            Signal.source_id,
            func.count(),
            func.count().filter(Signal.published_at >= since),
        ).group_by(Signal.source_id)
    ).all()
    return {r[0]: (r[1], r[2]) for r in rows}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30] or "feed"


def add_feed(db: Session, *, actor: User, data: dict[str, Any], ip_address: str | None) -> Source:
    base = _slug(data["name"])
    key, n = base, 2
    while db.scalar(select(Source.id).where(Source.key == key)) is not None:
        key, n = f"{base}-{n}", n + 1
    source = Source(
        id=uuid.uuid4(),
        key=key,
        name=data["name"],
        source_type=SourceType.NEWS,
        adapter=Adapter.RSS,
        url=data["url"],
        domain=re.sub(r"^https?://(www\.)?", "", data["url"]).split("/")[0][:120],
        language=data["language"],
        enabled=True,
        interval_minutes=data["interval_minutes"],
    )
    db.add(source)
    db.flush()
    audit.record(
        db,
        audit.AuditAction.SOURCE_CREATED,
        actor_id=actor.id,
        target_type="source",
        target_id=source.id,
        ip_address=ip_address,
        details={"key": key, "url": source.url},
    )
    db.commit()
    db.refresh(source)
    return source


def update_source(
    db: Session, *, actor: User, source: Source, changes: dict[str, Any], ip_address: str | None
) -> Source:
    diff = {}
    for field, new in changes.items():
        old = getattr(source, field)
        if old != new:
            diff[field] = [old, new]
            setattr(source, field, new)
    if diff:
        audit.record(
            db,
            audit.AuditAction.SOURCE_UPDATED,
            actor_id=actor.id,
            target_type="source",
            target_id=source.id,
            ip_address=ip_address,
            details={"key": source.key, "changes": diff},
        )
        db.commit()
        db.refresh(source)
    return source
