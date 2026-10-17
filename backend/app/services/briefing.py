"""Decision support for an event (module 6, app/decision_support): a suggested priority
from operational factors, a summary whose every sentence cites evidence, and what
changed since a moment.

This module turns the database into the plain values the decision support module
reads: each linked item with its source, stance, details and its source's reliability
(as the assessment rates it), which items repeat another, and the fused estimate of
each detail. Field workers are "A field worker", never named (Spec §8.3).
"""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.decision_support import (
    Detail,
    Estimate,
    EventFacts,
    Evidence,
    LogEntry,
    suggest,
    summarise,
    what_changed,
)
from app.decision_support.priority import PrioritySuggestion
from app.models.audit import AuditLog
from app.models.event import Event, EventEvidence
from app.services import assess, audit, details
from app.services import copies as copy_detection

FIELD_WORKER = "A field worker"
CHANGE_WORDS = {"status": "Status", "priority": "Priority", "assessment": "Assessment"}


def _evidence(link: EventEvidence, rate, copy_of: str | None) -> Evidence:
    relation = link.gold_relation or link.relation
    conflicts = link.gold_conflicts if link.gold_relation is not None else link.conflicts
    if link.field_report is not None:
        r = link.field_report
        source, kind, at, headline = FIELD_WORKER, "field", r.received_at, ""
        key, stated = f"reporter:{r.reporter_id}", details.for_report(r)
    else:
        s = link.signal
        source, kind, at = s.source.name, s.source.source_type.value, s.published_at
        headline, stated = s.title, details.for_signal(s)
        key = f"source:{s.source_id}"
    vote = assess._vote(link)
    denial = next((c.surface for c in stated if c.attribute == "occurrence" and not c.value), "")
    return Evidence(
        id=str(link.id),
        source=source,
        kind=kind,
        relation=relation.value,
        at=at,
        headline=headline[:200],
        conflicts=tuple(str(c) for c in conflicts or ()),
        details=tuple(
            Detail(c.attribute, c.value, c.unit, c.surface)
            for c in stated
            if c.attribute != "occurrence"
        ),
        reliability=rate(vote)[0] if vote is not None else None,
        copy_of=copy_of,
        denial=denial,
        source_key=key,
    )


def facts(db: Session, event: Event) -> EventFacts:
    """The event as decision support reads it."""
    s = assess.suggest(db, event)
    weights, _ = assess.current_weights(db)
    found = copy_detection.resolved(db, event)
    return EventFacts(
        id=str(event.id),
        title=event.title,
        event_type=event.event_type,
        family=event.family,
        place_name=event.place_name,
        started_at=event.started_at,
        ended_at=event.ended_at,
        status=event.status.value,
        assessment=event.assessment.value,
        suggested=s.label.value,
        probability=s.probability,
        estimates=[Estimate(d.attribute, d.estimate, d.unit, d.disputed) for d in s.details],
        evidence=[
            _evidence(
                link,
                weights.rate,
                str(found[link.id].origin_evidence_id) if link.id in found else None,
            )
            for link in event.evidence
        ],
    )


def priority(db: Session, event: Event, now: datetime) -> PrioritySuggestion:
    return suggest(facts(db, event), now)


def _log(db: Session, event: Event) -> list[LogEntry]:
    """Analysts' decisions on the event, as plain sentences (no names)."""
    rows = db.scalars(
        select(AuditLog)
        .where(
            AuditLog.target_type == "event",
            AuditLog.target_id == str(event.id),
            AuditLog.action == audit.AuditAction.EVENT_UPDATED,
        )
        .order_by(AuditLog.occurred_at)
    ).all()
    out = []
    for row in rows:
        for field, (_, new) in (row.details or {}).get("changes", {}).items():
            if field in CHANGE_WORDS and new is not None:
                words = str(new).replace("_", " ")
                out.append(LogEntry(row.occurred_at, f"{CHANGE_WORDS[field]} set to {words}."))
    return out


def briefing(db: Session, event: Event, now: datetime, since: datetime) -> dict[str, Any]:
    f = facts(db, event)
    p = suggest(f, now)
    return {
        "generated_at": now,
        "since": since,
        "priority": {
            "level": p.level,
            "score": p.score,
            "factors": [
                {"name": x.name, "points": x.points, "reason": x.reason} for x in p.factors
            ],
        },
        "summary": [_sentence(x) for x in summarise(f, now)],
        "changes": [_sentence(x) for x in what_changed(f, since, now, _log(db, event))],
    }


def _sentence(x) -> dict[str, Any]:
    return {"text": x.text, "cites": list(x.cites), "kind": x.kind}


def for_audit(p: PrioritySuggestion, chosen: str) -> dict[str, Any]:
    """What is written to the audit log when an analyst sets a priority."""
    return {"level": p.level, "score": p.score, "followed": p.level == chosen}


# --- How often analysts follow the suggested priority ----------------------------------

LEVELS = ["low", "medium", "high", "critical"]


def evaluate(db: Session) -> dict[str, Any]:
    """Suggested against chosen priority, from the audit log: how often they agree,
    and how far apart they are when they do not (in levels)."""
    shown = [
        (d["priority_suggestion"]["level"], d["changes"]["priority"][1])
        for d in db.scalars(
            select(AuditLog.details).where(
                AuditLog.action == audit.AuditAction.EVENT_UPDATED,
                AuditLog.details["priority_suggestion"].is_not(None),
            )
        ).all()
    ]
    confusion = {chosen: dict.fromkeys(LEVELS, 0) for chosen in LEVELS}
    for suggested, chosen in shown:
        confusion[chosen][suggested] += 1
    gaps = [LEVELS.index(s) - LEVELS.index(c) for s, c in shown]
    return {
        "shown": len(shown),
        "followed": sum(s == c for s, c in shown),
        "within_one_level": sum(abs(g) <= 1 for g in gaps),
        "suggested_higher": sum(g > 0 for g in gaps),
        "suggested_lower": sum(g < 0 for g in gaps),
        "confusion": confusion,  # chosen -> suggested -> count
    }


def table(result: dict[str, Any]) -> str:
    n = result["shown"]
    if not n:
        return "No priorities set with a suggestion shown yet."
    lines = [
        f"Priorities set with a suggestion shown: {n}",
        f"  followed {result['followed']} ({result['followed'] / n:.0%}), "
        f"within one level {result['within_one_level']} ({result['within_one_level'] / n:.0%})",
        f"  suggested higher than chosen {result['suggested_higher']}, "
        f"lower {result['suggested_lower']}",
        "",
        "  chosen \\ suggested  " + "  ".join(f"{x:>8}" for x in LEVELS),
    ]
    for chosen in LEVELS:
        row = result["confusion"][chosen]
        lines.append(f"  {chosen:<19}" + "  ".join(f"{row[s]:>8}" for s in LEVELS))
    return "\n".join(lines)


DEFAULT_SINCE = timedelta(hours=24)
