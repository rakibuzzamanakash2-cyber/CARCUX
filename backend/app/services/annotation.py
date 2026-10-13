"""Second opinions, agreement and adjudication (annotation guideline, section 7).

Every link between an item and an event should be judged independently by two
annotators. The person who links an item gives the first judgement; a second analyst
gives theirs blind, from a queue that does not show the first label. Agreement is
measured on the relation labels, and disagreements are resolved into a gold label.
"""

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.event import Event, EventEvidence, EventStatus, EvidenceJudgement, EvidenceRelation
from app.models.user import User
from app.schemas.event import NO_CLAIM
from app.services import audit

LABELS = [r.value for r in EvidenceRelation]
TARGET_KAPPA = 0.70  # guideline 7.2, before scaling up


class InvalidJudgementError(Exception):
    pass


def check_labels(relation: EvidenceRelation, conflicts: list[str]) -> None:
    if relation == EvidenceRelation.PARTIALLY_SUPPORTS and not conflicts:
        raise InvalidJudgementError("Say what it gets wrong: partly supports needs a conflict")
    if relation in NO_CLAIM and conflicts:
        raise InvalidJudgementError("Related-only and unrelated items have no conflicts")


def _judged_by(user_id: uuid.UUID):
    return select(EvidenceJudgement.evidence_id).where(EvidenceJudgement.annotator_id == user_id)


def _judgement_count():
    return (
        select(func.count(EvidenceJudgement.id))
        .where(EvidenceJudgement.evidence_id == EventEvidence.id)
        .scalar_subquery()
    )


def queue(db: Session, user: User, *, limit: int, offset: int) -> tuple[list[EventEvidence], int]:
    """Links this user has not judged, with fewer than two judgements, oldest first.
    Links on dismissed events are left out."""
    query = (
        select(EventEvidence)
        .join(Event, Event.id == EventEvidence.event_id)
        .where(
            EventEvidence.id.not_in(_judged_by(user.id)),
            _judgement_count() < 2,
            Event.status != EventStatus.DISMISSED,
        )
    )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(EventEvidence.linked_at, EventEvidence.id).limit(limit).offset(offset)
    ).all()
    return list(items), total


def judge(
    db: Session,
    *,
    actor: User,
    item: EventEvidence,
    relation: EvidenceRelation,
    conflicts: list[str],
    stale: bool,
    confidence: int,
    note: str | None,
    ip_address: str | None,
) -> EvidenceJudgement:
    """Record (or replace) this annotator's own judgement. The working label is untouched."""
    check_labels(relation, conflicts)
    mine = next((j for j in item.judgements if j.annotator_id == actor.id), None)
    if mine is None:
        mine = EvidenceJudgement(annotator_id=actor.id, blind=True)
        item.judgements.append(mine)
    mine.relation = relation
    mine.conflicts = [str(c) for c in conflicts]
    mine.stale = stale
    mine.confidence = confidence
    mine.note = note
    audit.record(
        db,
        audit.AuditAction.EVIDENCE_JUDGED,
        actor_id=actor.id,
        target_type="event",
        target_id=item.event_id,
        ip_address=ip_address,
        details={"evidence_id": str(item.id), "relation": relation.value},
    )
    db.commit()
    db.refresh(mine)
    return mine


# --- Agreement ---------------------------------------------------------------------------


def _key(j: EvidenceJudgement) -> str:
    return j.relation.value


def cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Cohen's κ for two ratings per item (nominal labels)."""
    n = len(pairs)
    if n == 0:
        return None
    observed = sum(a == b for a, b in pairs) / n
    first, second = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum(first[k] * second[k] for k in set(first) | set(second)) / (n * n)
    if expected == 1:
        return 1.0 if observed == 1 else None
    return (observed - expected) / (1 - expected)


def krippendorff_alpha(units: list[list[str]]) -> float | None:
    """Krippendorff's α (nominal) for units with two or more ratings each.
    Handles more than two annotators and different annotators per unit."""
    units = [u for u in units if len(u) >= 2]
    if not units:
        return None
    coincidence: Counter = Counter()
    for values in units:
        m = len(values)
        counts = Counter(values)
        for c in counts:
            for k in counts:
                pairs = counts[c] * (counts[k] - (1 if c == k else 0))
                coincidence[(c, k)] += pairs / (m - 1)
    n_c: Counter = Counter()
    for (c, _k), v in coincidence.items():
        n_c[c] += v
    n = sum(n_c.values())
    if n <= 1:
        return None
    observed = sum(v for (c, k), v in coincidence.items() if c != k)
    expected = sum(n_c[c] * n_c[k] for c in n_c for k in n_c if c != k) / (n - 1)
    if expected == 0:
        return 1.0 if observed == 0 else None
    return 1 - observed / expected


@dataclass
class Agreement:
    items_with_two: int
    items_total: int
    percent: float | None
    kappa: float | None
    alpha: float | None
    target: float
    matrix: dict[str, dict[str, int]]  # first annotator's label -> second's -> count
    by_label: dict[str, int]


def agreement(db: Session) -> Agreement:
    links = db.scalars(select(EventEvidence)).all()
    units = [[_key(j) for j in link.judgements] for link in links]
    doubled = [u for u in units if len(u) >= 2]
    pairs = [(u[0], u[1]) for u in doubled]
    matrix = {a: dict.fromkeys(LABELS, 0) for a in LABELS}
    for a, b in pairs:
        matrix[a][b] += 1
    return Agreement(
        items_with_two=len(doubled),
        items_total=len(units),
        percent=(sum(a == b for a, b in pairs) / len(pairs)) if pairs else None,
        kappa=cohen_kappa(pairs),
        alpha=krippendorff_alpha(doubled),
        target=TARGET_KAPPA,
        matrix=matrix,
        by_label=dict(Counter(label for u in units for label in u)),
    )


def disagrees(link: EventEvidence) -> bool:
    """Two or more judgements that differ in label, or in conflicts for partly supports."""
    js = link.judgements
    if len(js) < 2:
        return False
    if len({j.relation for j in js}) > 1:
        return True
    return len({tuple(sorted(j.conflicts or [])) for j in js}) > 1


def disagreements(db: Session, *, include_resolved: bool = False) -> list[EventEvidence]:
    links = db.scalars(select(EventEvidence).order_by(EventEvidence.linked_at)).all()
    return [
        link
        for link in links
        if disagrees(link) and (include_resolved or link.gold_relation is None)
    ]


def agreed_label(link: EventEvidence) -> tuple[EvidenceRelation, list[str]] | None:
    """The label everyone gave, if at least two annotators gave the same one."""
    if len(link.judgements) >= 2 and not disagrees(link):
        first = link.judgements[0]
        return first.relation, sorted(first.conflicts or [])
    return None


def adjudicate(
    db: Session,
    *,
    actor: User,
    item: EventEvidence,
    relation: EvidenceRelation,
    conflicts: list[str],
    note: str | None,
    ip_address: str | None,
) -> EventEvidence:
    """Resolve a disagreement into the gold label; the working label follows it."""
    check_labels(relation, conflicts)
    before: dict[str, Any] = {
        "judgements": [j.relation.value for j in item.judgements],
        "working": item.relation.value,
    }
    item.gold_relation = relation
    item.gold_conflicts = [str(c) for c in conflicts]
    item.gold_by_id = actor.id
    item.gold_at = datetime.now(UTC)
    item.relation = relation
    item.conflicts = [str(c) for c in conflicts]
    if note:
        item.note = note
    audit.record(
        db,
        audit.AuditAction.EVIDENCE_ADJUDICATED,
        actor_id=actor.id,
        target_type="event",
        target_id=item.event_id,
        ip_address=ip_address,
        details={
            "evidence_id": str(item.id),
            **before,
            "gold": relation.value,
            **({"conflicts": item.gold_conflicts} if conflicts else {}),
        },
    )
    db.commit()
    db.refresh(item)
    return item
