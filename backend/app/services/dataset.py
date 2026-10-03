"""Export CARCUX's records as a CARCUX-BD dataset (data/schema/v1).

What goes where:

- events.jsonl: events whose ground truth is recorded (occurred yes/no and at least one
  post-event source). Assessments at T+1h, T+6h, T+24h after the first linked item and
  a final one are reconstructed from the audit log: the label the analyst had set at
  that moment.
- observations.jsonl: field reports and public signals linked to an exported event
  (or every one, with include_unlinked).
- relations.jsonl: each link, with the analyst's relation, conflicts, stale flag and
  confidence.
- dependences.jsonl: reused photos flagged at submission (same_media).
- sources.jsonl: one source per publisher, and one per field worker (named only
  "Field worker").

People never appear by name: annotators are ANN-001, ANN-002, ... in order of account
creation, and ANN-000 stands for CARCUX's own automatic checks. Phone numbers and email
addresses are removed from field report text; names of private individuals are not
detectable automatically, so field report text must be read before a dataset is
published (the manifest says so).

Records that cannot be exported yet are listed as problems, so analysts can fix them.
"""

import json
import math
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import __version__
from app.core.event_types import BD_LAT, BD_LON
from app.ingest.places import PRECISION_M, gazetteer
from app.models.audit import AuditLog
from app.models.event import Event, EventEvidence, EvidenceRelation
from app.models.field_report import FieldReport
from app.models.signal import EXCERPT_MAX, Signal, Source
from app.models.user import User

SCHEMA_VERSION = "1.1"
GUIDELINE_VERSION = "0.2"
DHAKA = timezone(timedelta(hours=6))
CHECKPOINTS = [("T+1h", timedelta(hours=1)), ("T+6h", timedelta(hours=6)),
               ("T+24h", timedelta(hours=24))]  # fmt: skip
AUTOMATIC = "ANN-000"  # CARCUX's own checks (e.g. photo hashes)
EVENT_PRECISION_M = 1_000.0
FIELD_PRECISION_M = 50.0

_PHONE = re.compile(r"(?:\+?88)?01[3-9]\d{8}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_BANGLA = re.compile(r"[ঀ-৿]")
# Common Banglish words: enough to tell "Mirpur 10 e pani" from English.
_BANGLISH = re.compile(
    r"\b(pani|ache|achhe|hocche|hoise|hoyeche|rasta|bondho|jome|jam|kono|onek|manush|"
    r"gari|cholche|na|e|te|theke|dekhlam|ekhane|ekhon|agun|lagse|lagche|vore|bristi)\b",
    re.IGNORECASE,
)


@dataclass
class Problem:
    kind: str  # needs_ground_truth, needs_conflicts, outside_bangladesh, ...
    message: str
    event_id: str | None = None
    evidence_id: str | None = None


@dataclass
class Export:
    files: dict[str, list[dict[str, Any]]]
    manifest: dict[str, Any]
    id_map: dict[str, str]  # internal id -> dataset id (keep private)
    problems: list[Problem] = field(default_factory=list)


def _iso(dt: datetime) -> str:
    return dt.astimezone(DHAKA).isoformat(timespec="seconds")


def _in_bangladesh(lat: float, lon: float) -> bool:
    return BD_LAT[0] <= lat <= BD_LAT[1] and BD_LON[0] <= lon <= BD_LON[1]


def _nearest_district(lat: float, lon: float) -> dict:
    """The district whose centre is nearest: an approximation for admin names."""
    return min(
        gazetteer()["districts"],
        key=lambda d: (d["lat"] - lat) ** 2 + ((d["lon"] - lon) * math.cos(math.radians(lat))) ** 2,
    )


def _admin(lat: float, lon: float, district: str | None, locality: str | None) -> dict:
    by_name = {d["name"]: d for d in gazetteer()["districts"]}
    d = by_name.get(district or "") or _nearest_district(lat, lon)
    admin = {"division": d["division"], "district": d["name"]}
    if locality and locality not in (d["name"], d["division"]):
        admin["locality"] = locality[:200]
    return admin


def _location(lat, lon, precision_m, district=None, locality=None) -> dict:
    return {
        "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
        "precision_m": max(float(precision_m or EVENT_PRECISION_M), 1.0),
        "admin": _admin(lat, lon, district, locality),
    }


def _language(text: str) -> str:
    if _BANGLA.search(text):
        return "mixed" if re.search(r"[A-Za-z]{4,}", text) else "bn"
    return "bn-Latn" if len(_BANGLISH.findall(text)) >= 2 else "en"


def _redact(text: str) -> str:
    return _EMAIL.sub("[EMAIL]", _PHONE.sub("[PHONE]", text))


def _claims(event_type: str | None) -> list[dict]:
    claims = [{"attribute": "occurrence", "value": True}]
    if event_type:
        claims.append({"attribute": "event_type", "value": event_type})
    return claims


class _Ids:
    """Dataset ids handed out in a fixed order, remembered for the id map."""

    def __init__(self, prefix: str, width: int):
        self.prefix, self.width, self.map = prefix, width, {}

    def __call__(self, key: str) -> str:
        if key not in self.map:
            self.map[key] = f"{self.prefix}-{len(self.map) + 1:0{self.width}d}"
        return self.map[key]


def build(db: Session, *, include_unlinked: bool = False, now: datetime | None = None) -> Export:
    now = now or datetime.now(UTC)
    problems: list[Problem] = []

    users = db.scalars(select(User).order_by(User.created_at, User.id)).all()
    annotator = {u.id: f"ANN-{i:03d}" for i, u in enumerate(users, start=1) if i <= 999}

    def ann(user_id, at: datetime, confidence: int, **extra) -> dict:
        return {
            "annotator": annotator.get(user_id, AUTOMATIC),
            "confidence": confidence,
            "annotated_at": _iso(at),
            "guideline_version": GUIDELINE_VERSION,
            **extra,
        }

    # --- Events: only those with ground truth ----------------------------------------
    all_events = db.scalars(select(Event).order_by(Event.created_at, Event.id)).all()
    events = []
    for ev in all_events:
        if ev.occurred is None or not ev.ground_truth_sources:
            problems.append(
                Problem(
                    "needs_ground_truth",
                    "Record whether it happened and at least one source published afterwards.",
                    event_id=str(ev.id),
                )
            )
            continue
        if not ev.occurred and ev.assessment.value == "verified":
            problems.append(
                Problem(
                    "contradiction",
                    "Assessed as verified, but the ground truth says it did not happen.",
                    event_id=str(ev.id),
                )
            )
            continue
        if not _in_bangladesh(ev.latitude, ev.longitude):
            problems.append(Problem("outside_bangladesh", "Location outside Bangladesh.",
                                    event_id=str(ev.id)))  # fmt: skip
            continue
        events.append(ev)
    event_ids = _Ids("EVT", 6)
    for ev in events:
        event_ids(str(ev.id))

    # --- Which evidence goes in --------------------------------------------------------
    links: list[EventEvidence] = [item for ev in events for item in ev.evidence]
    report_ids = {i.field_report_id for i in links if i.field_report_id}
    signal_ids = {i.signal_id for i in links if i.signal_id}
    if include_unlinked:
        report_ids |= set(db.scalars(select(FieldReport.id)))
        signal_ids |= set(db.scalars(select(Signal.id)))
    reports = (
        db.scalars(select(FieldReport).where(FieldReport.id.in_(report_ids))).all()
        if report_ids
        else []
    )
    signals = (
        db.scalars(select(Signal).where(Signal.id.in_(signal_ids))).all() if signal_ids else []
    )

    # --- Sources -----------------------------------------------------------------------
    source_ids = _Ids("SRC", 6)
    sources_out = []
    publishers = db.scalars(select(Source).order_by(Source.created_at, Source.key)).all()
    used_publishers = {s.source_id for s in signals}
    for src in publishers:
        if src.id not in used_publishers:
            continue
        sources_out.append(
            {
                "source_id": source_ids(f"source:{src.id}"),
                "source_type": src.source_type.value,
                "name": src.name,
                **({"domain": src.domain} if src.domain else {}),
                "languages": [src.language],
            }
        )
    for reporter_id in sorted({str(r.reporter_id) for r in reports}):
        sources_out.append(
            {
                "source_id": source_ids(f"reporter:{reporter_id}"),
                "source_type": "field",
                "name": "Field worker",
            }
        )

    # --- Observations, in publication order -----------------------------------------
    items: list[tuple[datetime, str, Any]] = [(r.received_at, f"r:{r.id}", r) for r in reports]
    items += [(s.published_at, f"s:{s.id}", s) for s in signals]
    items.sort(key=lambda x: (x[0], x[1]))
    obs_ids = _Ids("OBS", 7)
    observations, published = [], {}
    for when, key, obj in items:
        oid = obs_ids(key)
        published[key] = when
        if isinstance(obj, FieldReport):
            observations.append(_report_observation(oid, obj, source_ids))
        else:
            observations.append(_signal_observation(oid, obj, source_ids))

    # --- Relations -----------------------------------------------------------------------
    last_change = _last_evidence_change(db)
    relations = []
    for item in links:
        key = f"r:{item.field_report_id}" if item.field_report_id else f"s:{item.signal_id}"
        if item.relation == EvidenceRelation.PARTIALLY_SUPPORTS and not item.conflicts:
            problems.append(
                Problem(
                    "needs_conflicts",
                    "Partly supports: say which attributes it gets wrong.",
                    event_id=str(item.event_id),
                    evidence_id=str(item.id),
                )
            )
            continue
        judgement: dict[str, Any] = {"label": item.relation.value}
        if item.conflicts and item.relation != EvidenceRelation.RELATED:
            judgement["conflicts"] = list(item.conflicts)
        if item.stale:
            judgement["stale"] = True
        changed_by, changed_at = last_change.get(item.id, (item.linked_by_id, item.linked_at))
        relations.append(
            {
                "obs_id": obs_ids(key),
                "event_id": event_ids(str(item.event_id)),
                "annotations": [ann(changed_by, changed_at, item.confidence, **judgement)],
            }
        )

    # --- Dependences: photos reused from an earlier report -----------------------------
    dependences = []
    for r in sorted(reports, key=lambda r: r.received_at):
        for flag in r.integrity_flags:
            if flag.get("code") != "photo_reused":
                continue
            m = _UUID.search(flag.get("detail", ""))
            origin_key = f"r:{m.group(0)}" if m else None
            if origin_key not in published or published[origin_key] > r.received_at:
                continue
            identical = "identical" in flag.get("detail", "") and "nearly" not in flag["detail"]
            dependences.append(
                {
                    "obs_id": obs_ids(f"r:{r.id}"),
                    "origin_obs_id": obs_ids(origin_key),
                    "type": "same_media",
                    "evidence": ["media_hash", "timestamp_order"],
                    "annotations": [
                        ann(
                            None,
                            r.received_at,
                            3 if identical else 2,
                            note="Detected automatically by photo hash at submission",
                        )
                    ],  # fmt: skip
                }
            )
            break  # only the item it was directly copied from

    # --- Events with reconstructed assessments ----------------------------------------
    history = _assessment_history(db)
    events_out = []
    for ev in events:
        linked_times = [published[f"r:{i.field_report_id}"] if i.field_report_id
                        else published[f"s:{i.signal_id}"] for i in ev.evidence
                        if (f"r:{i.field_report_id}" if i.field_report_id
                            else f"s:{i.signal_id}") in published]  # fmt: skip
        first = min(linked_times) if linked_times else ev.started_at
        events_out.append(_event_record(ev, event_ids, first, now, history, ann))

    files = {
        "events.jsonl": events_out,
        "sources.jsonl": sources_out,
        "observations.jsonl": observations,
        "relations.jsonl": relations,
        "dependences.jsonl": dependences,
    }
    manifest = {
        "dataset": "CARCUX-BD",
        "schema_version": SCHEMA_VERSION,
        "guideline_version": GUIDELINE_VERSION,
        "exported_at": _iso(now),
        "exported_by": f"CARCUX {__version__}",
        "counts": {name: len(rows) for name, rows in files.items()},
        "include_unlinked": include_unlinked,
        "annotators": {
            "ANN-000": "CARCUX automatic checks",
            "others": "Pseudonymous CARCUX accounts, numbered in order of account creation",
        },
        "assessments": "Reconstructed from the audit log: the label set in CARCUX at each "
        "checkpoint after the first linked item (T+1h, T+6h, T+24h) and at export (final).",
        "privacy": "Phone numbers and email addresses were removed from field report text. "
        "Read field report text and replace names of private individuals with [PERSON] "
        "before publishing.",
        "problems": len(problems),
    }
    id_map = {
        **{f"event:{k}": v for k, v in event_ids.map.items()},
        **{
            k.replace("r:", "field_report:").replace("s:", "signal:"): v
            for k, v in obs_ids.map.items()
        },  # fmt: skip
        **source_ids.map,
    }
    return Export(files=files, manifest=manifest, id_map=id_map, problems=problems)


def _report_observation(oid: str, r: FieldReport, source_ids: _Ids) -> dict:
    text = _redact(r.text)
    lat, lon = r.latitude, r.longitude
    ob: dict[str, Any] = {
        "obs_id": oid,
        "source_id": source_ids(f"reporter:{r.reporter_id}"),
        "modality": "mixed" if r.media else "text",
        "language": _language(text),
        "reference": f"carcux:field_report:{r.id}",
        "published_at": _iso(r.received_at),
        "observed_at": _iso(r.observed_at),
        "collected_at": _iso(r.received_at),
        "content_policy": "full",
        "text": text,
        "claims": _claims(r.event_type),
        "is_simulated": False,
    }
    if _in_bangladesh(lat, lon):
        ob["location_mentions"] = [
            {
                "surface": (r.place_name or "GPS position")[:200],
                "resolved": _location(
                    lat, lon, r.location_accuracy_m or FIELD_PRECISION_M, locality=r.place_name
                ),
                "from_gps": True,
            }
        ]
    if r.media:
        ob["media"] = [{"kind": "image", "phash": m.dhash.lower()} for m in r.media]
    return ob


def _signal_observation(oid: str, s: Signal, source_ids: _Ids) -> dict:
    ob: dict[str, Any] = {
        "obs_id": oid,
        "source_id": source_ids(f"source:{s.source_id}"),
        "modality": "text",
        "language": s.language,
        "reference": s.url or f"carcux:signal:{s.id}",
        "published_at": _iso(s.published_at),
        "collected_at": _iso(max(s.collected_at, s.published_at)),
        "claims": _claims(s.event_type),
        "is_simulated": False,
    }
    if s.text:
        # Excerpts only, whatever was stored: news is copyrighted, bulletins may be long.
        text = s.text if len(s.text) <= EXCERPT_MAX else s.text[: EXCERPT_MAX - 1] + "…"
        ob["content_policy"] = "excerpt"
        ob["text"] = text
    else:
        ob["content_policy"] = "reference_only"
    if (
        s.latitude is not None
        and s.longitude is not None
        and _in_bangladesh(s.latitude, s.longitude)
    ):
        surface = str(s.extraction.get("place_as_written") or s.place_name or s.district or "")
        ob["location_mentions"] = [
            {
                "surface": (surface or "Area of the alert")[:200],
                "resolved": _location(
                    s.latitude,
                    s.longitude,
                    s.precision_m or PRECISION_M["district"],
                    district=s.district,
                    locality=s.place_name,
                ),
            }
        ]
    return ob


def _last_evidence_change(db: Session) -> dict[uuid.UUID, tuple[uuid.UUID | None, datetime]]:
    """Who last changed each link's labels, and when (from the audit log)."""
    out = {}
    rows = db.execute(
        select(AuditLog.details, AuditLog.actor_id, AuditLog.occurred_at)
        .where(AuditLog.action == "event.evidence_updated")
        .order_by(AuditLog.occurred_at)
    ).all()
    for details, actor, at in rows:
        try:
            out[uuid.UUID(details["evidence_id"])] = (actor, at)
        except (KeyError, ValueError):
            continue
    return out


def _assessment_history(db: Session) -> dict[str, list[tuple[datetime, str, str, Any]]]:
    """Per event: (time, old label, new label, actor) for every assessment change."""
    out: dict[str, list] = defaultdict(list)
    rows = db.execute(
        select(AuditLog.target_id, AuditLog.details, AuditLog.occurred_at, AuditLog.actor_id)
        .where(AuditLog.action == "event.updated", AuditLog.target_type == "event")
        .order_by(AuditLog.occurred_at)
    ).all()
    for target, details, at, actor in rows:
        change = (details.get("changes") or {}).get("assessment")
        if change:
            out[target].append((at, change[0], change[1], actor))
    return out


def _event_record(ev: Event, event_ids: _Ids, first: datetime, now: datetime, history, ann):
    changes = history.get(str(ev.id), [])
    initial = changes[0][1] if changes else ev.assessment.value

    def label_at(t: datetime) -> tuple[str, Any, datetime]:
        label, actor, when = initial, ev.created_by_id, ev.created_at
        for at, _old, new, who in changes:
            if at <= t:
                label, actor, when = new, who, at
        return label, actor, when

    def count_at(t: datetime) -> tuple[int, int]:
        linked = [i for i in ev.evidence if i.linked_at <= t]
        sup = sum(i.relation.value in ("supports", "partially_supports") for i in linked)
        con = sum(i.relation.value == "contradicts" for i in linked)
        return sup, con

    assessments = []
    stamps = [(name, first + delta) for name, delta in CHECKPOINTS if first + delta <= now]
    final_at = max([now, *[t for _, t in stamps]])
    stamps.append(("final", final_at))
    for name, t in stamps:
        label, actor, when = label_at(t)
        sup, con = count_at(t)
        assessments.append(
            {
                "as_of": _iso(t),
                "checkpoint": name,
                "label": label,
                "rationale": (
                    f"Analyst assessment in CARCUX at {name}: {sup} supporting and {con} "
                    "contradicting item(s) linked by then."
                ),
                "annotations": [
                    ann(
                        actor,
                        max(when, ev.created_at),
                        2,
                        label=label,
                        note="Live analyst decision, reconstructed from the audit log",
                    )
                ],  # fmt: skip
            }
        )

    record: dict[str, Any] = {
        "event_id": event_ids(str(ev.id)),
        "family": ev.family,
        "type": ev.event_type,
        "title": ev.title,
        "location": _location(
            ev.latitude, ev.longitude, EVENT_PRECISION_M, locality=ev.place_name
        ),  # fmt: skip
        "start": _iso(ev.started_at),
        "time_precision": "hour",
        "ground_truth": {
            "occurred": bool(ev.occurred),
            "facts": [{"attribute": "occurrence", "value": bool(ev.occurred)}],
            "sources": [
                {
                    "reference": s["reference"],
                    "published_at": _iso(datetime.fromisoformat(s["published_at"])),
                    "kind": s["kind"],
                }
                for s in ev.ground_truth_sources
            ],
        },
        "assessments": assessments,
    }
    if ev.ended_at:
        record["end"] = _iso(ev.ended_at)
    if ev.ground_truth_note:
        record["notes"] = ev.ground_truth_note
    return record


def write_jsonl(rows: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def to_zip(export: Export) -> bytes:
    """The five dataset files, the manifest and the problems, in one zip.

    The id map (CARCUX ids to dataset ids) is included as id_map.json: keep it with
    the project, not with a published copy of the dataset."""
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, rows in export.files.items():
            z.writestr(name, write_jsonl(rows))
        z.writestr("manifest.json", json.dumps(export.manifest, indent=2, ensure_ascii=False))
        z.writestr(
            "problems.json",
            json.dumps([p.__dict__ for p in export.problems], indent=2, ensure_ascii=False),
        )
        z.writestr("id_map.json", json.dumps(export.id_map, indent=2))
    return buf.getvalue()
