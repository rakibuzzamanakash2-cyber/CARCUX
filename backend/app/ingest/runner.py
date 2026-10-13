"""Read sources and store what they say as signals.

Each read is recorded as an IngestRun (counts, or the error), and the source keeps
its last run, last success and last error for the Sources page. Items are matched
by (source, external id): new ones are added; changed ones (a GDACS alert raised
from orange to red, a corrected headline) are updated, keeping the analyst's review.
"""

import hashlib
import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.event_types import EVENT_TYPE_FAMILY
from app.ingest import gdacs, reliefweb, rss
from app.ingest.base import FetchError, Item, Request, fetch
from app.models.signal import Adapter, IngestRun, Signal, Source
from app.models.user import User

log = logging.getLogger("carcux.ingest")

ADAPTERS = {Adapter.GDACS: gdacs, Adapter.RSS: rss, Adapter.RELIEFWEB: reliefweb}
Fetcher = Callable[[Request], bytes]


class NotReadableError(Exception):
    """Manual sources are entered by hand; there is nothing to fetch."""


class AlreadyRunningError(Exception):
    """Another read of this source is in progress."""


def default_fetcher(settings: Settings) -> Fetcher:
    def _fetch(request: Request) -> bytes:
        return fetch(
            request,
            timeout=settings.ingest_timeout_seconds,
            max_bytes=settings.ingest_max_bytes,
            allow_private=settings.ingest_allow_private_addresses,
        )

    return _fetch


def content_hash(item: Item) -> str:
    """Fingerprint of what the item says, to tell an update from a repeat."""
    fields = {
        "title": item.title,
        "text": item.text,
        "url": item.url,
        "event_type": item.event_type,
        "severity": item.severity.value if item.severity else None,
        "place": [item.place_name, item.latitude, item.longitude, item.precision_m],
        "valid": [
            item.valid_from.isoformat() if item.valid_from else None,
            item.valid_until.isoformat() if item.valid_until else None,
        ],
    }
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


_STORED = (
    "title", "text", "url", "content_policy", "language", "event_type", "severity",
    "place_name", "district", "latitude", "longitude", "precision_m", "published_at",
    "valid_from", "valid_until", "extraction",
)  # fmt: skip


def store(db: Session, source: Source, items: list[Item]) -> tuple[int, int]:
    """Add new items, update changed ones. Returns (created, updated)."""
    created = updated = 0
    ids = [i.external_id for i in items]
    existing = {
        s.external_id: s
        for s in db.scalars(
            select(Signal).where(Signal.source_id == source.id, Signal.external_id.in_(ids))
        )
    }
    for item in {i.external_id: i for i in items}.values():  # last one wins on repeats
        digest = content_hash(item)
        values = {k: getattr(item, k) for k in _STORED}
        values["family"] = EVENT_TYPE_FAMILY.get(item.event_type or "")
        signal = existing.get(item.external_id)
        if signal is None:
            db.add(
                Signal(
                    source_id=source.id,
                    external_id=item.external_id,
                    content_hash=digest,
                    **values,
                )
            )
            created += 1
        elif signal.content_hash != digest:
            for key, value in values.items():
                setattr(signal, key, value)
            signal.content_hash = digest
            updated += 1
    return created, updated


def run_source(
    db: Session,
    source: Source,
    settings: Settings,
    *,
    fetcher: Fetcher | None = None,
    actor: User | None = None,
) -> IngestRun:
    """Read one source now. Never raises for source problems: they go in the run."""
    if source.adapter == Adapter.MANUAL:
        raise NotReadableError
    # One reader per source at a time (the scheduler and "Fetch now" can overlap).
    got_lock = db.execute(
        text("SELECT pg_try_advisory_xact_lock(hashtext(:k))"), {"k": f"ingest:{source.key}"}
    ).scalar()
    if not got_lock:
        raise AlreadyRunningError

    adapter = ADAPTERS[source.adapter]
    fetcher = fetcher or default_fetcher(settings)
    now = datetime.now(UTC)
    run = IngestRun(
        source_id=source.id, started_at=now, triggered_by_id=actor.id if actor else None
    )
    db.add(run)
    try:
        parsed = adapter.parse(fetcher(adapter.request(source, settings)), source)
        run.fetched, run.skipped = parsed.fetched, parsed.skipped
        run.created, run.updated = store(db, source, parsed.items)
        run.ok = True
        source.last_success_at = now
        source.last_error = None
    except (FetchError, ValueError) as exc:
        run.error = source.last_error = str(exc)[:500]
    except Exception as exc:  # malformed feed and the like: record it, keep the worker alive
        log.exception("ingest failed for %s", source.key)
        run.error = source.last_error = f"Could not read the response ({type(exc).__name__})"
    run.finished_at = datetime.now(UTC)
    source.last_run_at = now
    db.commit()
    return run


def due_sources(db: Session, now: datetime | None = None) -> list[Source]:
    now = now or datetime.now(UTC)
    sources = db.scalars(
        select(Source).where(Source.enabled.is_(True), Source.adapter != Adapter.MANUAL)
    ).all()
    return [
        s
        for s in sources
        if s.last_run_at is None
        or s.last_run_at + timedelta(minutes=max(s.interval_minutes, 5)) <= now
    ]


def run_due(session_factory, settings: Settings, fetcher: Fetcher | None = None) -> list[IngestRun]:
    runs = []
    with session_factory() as db:
        for source in due_sources(db):
            try:
                run = run_source(db, source, settings, fetcher=fetcher)
            except AlreadyRunningError:
                db.rollback()
                continue
            log.info(
                "%s: ok=%s fetched=%s new=%s updated=%s skipped=%s %s",
                source.key, run.ok, run.fetched, run.created, run.updated, run.skipped,
                run.error or "",
            )  # fmt: skip
            runs.append(run)
    return runs


def loop(session_factory, settings: Settings, *, tick_seconds: int = 60) -> None:
    """Run due sources forever. Used by the ingest worker container."""
    log.info("ingest worker started")
    while True:
        try:
            run_due(session_factory, settings)
        except Exception:  # database restarting and the like: try again next tick
            log.exception("ingest tick failed")
        time.sleep(tick_seconds)
