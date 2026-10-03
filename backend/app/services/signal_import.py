"""Import a list of past news items collected by annotators (a CSV file).

News archives have no feed that goes back in time, and copying them wholesale would
be both against their terms and against the dataset's rules. Instead an annotator
collects the links for a case study and CARCUX stores what the live feeds store:
headline, a short excerpt, the link, and the type and place (given, or found the same
way as for live news).

Columns (header row required; only the first four are needed):

    url, title, published, publisher, excerpt, event_type, place, language, severity
"""

import csv
import io
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.event_types import EVENT_TYPE_FAMILY, EVENT_TYPES
from app.ingest.base import excerpt, plain
from app.ingest.classify import classify
from app.ingest.places import best_place
from app.models.signal import Adapter, ContentPolicy, Severity, Signal, Source, SourceType
from app.models.user import User
from app.services import audit

DHAKA = timezone(timedelta(hours=6))
MAX_ROWS = 2000
MAX_BYTES = 2 * 1024 * 1024
REQUIRED = ("url", "title", "published", "publisher")
LANGUAGES = {"en", "bn", "bn-Latn", "mixed"}
_BANGLA = re.compile(r"[ঀ-৿]")


class ImportFileError(Exception):
    """The file as a whole cannot be read (not CSV, missing columns, too big)."""


@dataclass
class RowResult:
    line: int
    status: str  # "add", "duplicate" or "error"
    title: str = ""
    message: str = ""
    event_type: str | None = None
    place: str | None = None
    publisher: str | None = None
    signal_id: str | None = None


@dataclass
class ImportResult:
    rows: list[RowResult] = field(default_factory=list)
    created_sources: list[str] = field(default_factory=list)

    def count(self, status: str) -> int:
        return sum(r.status == status for r in self.rows)


def _published(value: str) -> datetime | None:
    """2024-08-21, 2024-08-21 14:30, or full ISO 8601. Without a zone, Dhaka time."""
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            day = datetime.strptime(value, fmt).date()  # noqa: DTZ007 (zone added below)
            return datetime.combine(day, time(12, 0), DHAKA)
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=DHAKA)


def _domain(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url, flags=re.IGNORECASE).split("/")[0][:120]


def _source_for(db: Session, publisher: str, url: str, language: str, cache: dict) -> Source:
    key = publisher.casefold()
    if key in cache:
        return cache[key]
    source = db.scalar(select(Source).where(func.lower(Source.name) == key))
    if source is None:
        domain = _domain(url)
        source = db.scalar(
            select(Source).where(Source.domain == domain, Source.source_type == SourceType.NEWS)
        )
    if source is None:
        base = re.sub(r"[^a-z0-9]+", "-", key).strip("-")[:30] or "publisher"
        slug, n = base, 2
        while db.scalar(select(Source.id).where(Source.key == slug)) is not None:
            slug, n = f"{base}-{n}", n + 1
        source = Source(
            id=uuid.uuid4(),
            key=slug,
            name=publisher[:120],
            source_type=SourceType.NEWS,
            adapter=Adapter.MANUAL,
            domain=_domain(url),
            language=language,
            enabled=True,
            interval_minutes=0,
        )
        db.add(source)
        db.flush()
        cache.setdefault("_created", []).append(source.name)
    cache[key] = source
    return source


def import_csv(
    db: Session, *, actor: User, data: bytes, dry_run: bool, ip_address: str | None
) -> ImportResult:
    if len(data) > MAX_BYTES:
        raise ImportFileError("The file is larger than 2 MB; split it")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ImportFileError("Save the file as CSV UTF-8") from None
    reader = csv.DictReader(io.StringIO(text))
    headers = [h.strip().lower() for h in reader.fieldnames or []]
    missing = [c for c in REQUIRED if c not in headers]
    if missing:
        raise ImportFileError(f"Missing column(s): {', '.join(missing)}")

    result = ImportResult()
    cache: dict[str, Any] = {}
    seen_urls: set[str] = set()
    for line, raw in enumerate(reader, start=2):
        if line - 1 > MAX_ROWS:
            raise ImportFileError(f"At most {MAX_ROWS} rows per file")
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        if not any(row.values()):
            continue
        title = plain(row.get("title"))[:400]
        url = row.get("url", "")
        res = RowResult(line=line, status="error", title=title, publisher=row.get("publisher"))
        result.rows.append(res)

        if not re.match(r"^https?://\S+$", url, re.IGNORECASE):
            res.message = "url must be an http or https address"
            continue
        if len(title) < 5:
            res.message = "title is missing or too short"
            continue
        published = _published(row.get("published", ""))
        if published is None:
            res.message = "published must be a date like 2024-08-21"
            continue
        if not row.get("publisher"):
            res.message = "publisher is missing"
            continue
        language = row.get("language") or ("bn" if _BANGLA.search(title) else "en")
        if language not in LANGUAGES:
            res.message = f"language must be one of {', '.join(sorted(LANGUAGES))}"
            continue
        severity = row.get("severity", "").lower() or None
        if severity and severity not in {s.value for s in Severity}:
            res.message = "severity must be minor, moderate or severe"
            continue
        summary = plain(row.get("excerpt"))

        event_type = row.get("event_type") or None
        matched: list[str] = []
        if event_type and event_type not in EVENT_TYPES:
            res.message = f"unknown event_type '{event_type}'"
            continue
        if not event_type:
            kind = classify(title, summary)
            if kind is None:
                res.message = "could not tell the event type; fill in event_type"
                continue
            event_type, matched = kind.event_type, kind.matched
        place = best_place(row["place"]) if row.get("place") else best_place(title, summary)
        if row.get("place") and place is None:
            res.message = f"place '{row['place']}' is not a known district, upazila or area"
            continue
        res.event_type, res.place = event_type, place.name if place else None

        if url in seen_urls or db.scalar(select(Signal.id).where(Signal.url == url)):
            res.status, res.message = "duplicate", "already in CARCUX"
            continue
        seen_urls.add(url)
        source = _source_for(db, row["publisher"], url, language, cache)
        signal = Signal(
            id=uuid.uuid4(),
            source_id=source.id,
            external_id=url[:300],
            title=title,
            text=excerpt(summary),
            content_policy=ContentPolicy.EXCERPT,
            url=url[:1000],
            language=language,
            event_type=event_type,
            family=EVENT_TYPE_FAMILY[event_type],
            severity=severity,
            place_name=place.name if place else None,
            district=place.district if place else None,
            latitude=place.latitude if place else None,
            longitude=place.longitude if place else None,
            precision_m=place.precision_m if place else None,
            published_at=published,
            extraction={
                "method": "imported list",
                **({"matched": matched, "matched_in_headline": True} if matched else {}),
                **(
                    {"place_as_written": place.surface, "place_level": place.level} if place else {}
                ),
            },
            content_hash="",
            entered_by_id=actor.id,
        )
        db.add(signal)
        res.status, res.signal_id = "add", str(signal.id)

    result.created_sources = cache.get("_created", [])
    if dry_run:
        db.rollback()
        for r in result.rows:
            r.signal_id = None
        return result
    audit.record(
        db,
        audit.AuditAction.SIGNALS_IMPORTED,
        actor_id=actor.id,
        ip_address=ip_address,
        details={
            "added": result.count("add"),
            "duplicates": result.count("duplicate"),
            "errors": result.count("error"),
            "new_publishers": result.created_sources,
        },
    )
    db.commit()
    return result
