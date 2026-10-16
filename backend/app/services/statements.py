"""Official statements and the brief they are written from.

The brief is what CARCUX knows about an event, for an official deciding what to say:
the analysts' assessment, CARCUX's suggested assessment with how sure it is, the
evidence for and against, disputed details with the best estimates, and copies counted
once. Field workers are never named in it (they are "a field worker"); public sources
are named. The brief at publication is stored with the statement.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.event import Event, EventStatus
from app.models.official import PageStatus
from app.models.statement import Finding, Statement
from app.models.user import Role, User
from app.schemas.event import EventRead
from app.services import assess, audit

FIELD_WORKER = "A field worker"


class StatementError(ValueError):
    """A rule about statements was not met; the message says which."""


def _plain(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def brief(db: Session, event: Event) -> dict[str, Any]:
    s = assess.suggest(db, event)
    ev = EventRead.model_validate(event).model_dump(mode="json")

    def who(name: str, kind: str) -> str:
        return FIELD_WORKER if kind == "field" else name

    kinds = {r.source: r.kind for r in s.reasons}
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "event": {
            k: ev[k]
            for k in (
                "id",
                "title",
                "summary",
                "event_type",
                "family",
                "place_name",
                "latitude",
                "longitude",
                "started_at",
                "ended_at",
                "status",
                "assessment",
                "evidence_counts",
            )
        },  # fmt: skip
        "suggestion": {
            "label": _plain(s.label),
            "probability": s.probability,
            "method": s.method,
            "sources_supporting": s.sources_supporting,
            "sources_denying": s.sources_denying,
            "credible_supporting": s.credible_supporting,
            "credible_denying": s.credible_denying,
            "disputed": list(s.disputed),
            "counted_once": s.counted_once,
        },
        "details": [
            {
                "attribute": d.attribute,
                "estimate": d.estimate,
                "unit": d.unit,
                "disputed": d.disputed,
                "sources": len(d.statements),
                "values": sorted({str(x.value) for x in d.statements}),
            }
            for d in s.details
        ],
        "sources": [
            {
                "source": who(r.source, r.kind),
                "kind": r.kind,
                "says": "happened" if r.vote > 0 else "did not happen" if r.vote < 0 else "unclear",
                "reliability": round(r.reliability, 2),
                "disputes": list(r.disputed),
            }
            for r in s.reasons
        ],
        "field_workers": sum(1 for k in kinds.values() if k == "field"),
    }


def can_write(user: User) -> bool:
    return (
        user.role == Role.OFFICIAL
        and user.is_active
        and user.official_page is not None
        and user.official_page.status == PageStatus.VERIFIED
    )


def visible(statement: Statement, user: User) -> bool:
    return (
        statement.page.status == PageStatus.VERIFIED
        or user.role == Role.ADMIN
        or user.official_page_id == statement.page_id
    )


def superseded_by(db: Session, statement_ids: list[uuid.UUID]) -> dict[uuid.UUID, uuid.UUID]:
    if not statement_ids:
        return {}
    rows = db.execute(
        select(Statement.supersedes_id, Statement.id).where(
            Statement.supersedes_id.in_(statement_ids)
        )
    ).all()
    return dict(rows)


def publish(
    db: Session, *, author: User, event: Event, finding: Finding, title: str, body: str,
    supersedes_id: uuid.UUID | None, ip: str | None,
) -> Statement:  # fmt: skip
    if not can_write(author):
        raise StatementError("Only officials of a verified page can publish statements")
    if event.status == EventStatus.DISMISSED:
        raise StatementError("This event was dismissed")
    if supersedes_id is not None:
        old = db.get(Statement, supersedes_id)
        if old is None or old.page_id != author.official_page_id or old.event_id != event.id:
            raise StatementError("You can only correct your page's statement on this event")
        if superseded_by(db, [old.id]):
            raise StatementError("That statement was already corrected; correct the latest one")
    statement = Statement(
        id=uuid.uuid4(),
        page_id=author.official_page_id,
        event_id=event.id,
        author_id=author.id,
        finding=finding,
        title=title.strip(),
        body=body.strip(),
        supersedes_id=supersedes_id,
        informed_by_carcux=True,
        brief=brief(db, event),
    )
    db.add(statement)
    db.flush()
    audit.record(
        db, audit.AuditAction.STATEMENT_PUBLISHED, actor_id=author.id,
        target_type="event", target_id=event.id, ip_address=ip,
        details={"statement_id": str(statement.id), "page_id": str(statement.page_id),
                 "finding": finding.value, "supersedes": str(supersedes_id) if supersedes_id
                 else None, "carcux_label": statement.brief["suggestion"]["label"]},
    )  # fmt: skip
    return statement
