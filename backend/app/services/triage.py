"""Which events to check first: the review queue for analysts.

Analysts cannot re-check every open event at once. The queue puts first the events
where a check matters most: the ones that would hurt most if the team got them wrong,
and where one more piece of evidence could still change what the team believes.

For each open event (active or monitoring):

- **Probability** that it really happened, from the evidence linked so far, by the same
  model as the suggested assessment (services/assess.py), copies counted once.
- **Uncertainty**, 1 - |2p - 1|: 1 at 50 %, 0 when the model is sure either way. No
  evidence at all counts as fully uncertain.
- **What one more field report would do.** The probability if a field worker with no
  record yet (rated as field workers are) reported that it is happening, and if they
  reported that it is not. Each answer is weighted by how likely it is, given what is
  known now (p·r + (1 - p)·(1 - r) for "happening", r the field worker's reliability);
  the **chance a check changes the picture** is the chance that the answer moves the
  event across a line the assessment uses (at least 80 %: verified; at most 20 %:
  refuted; in between: open). An event with no evidence always changes.
- **Impact**: the priority the analysts set (low 1, medium 2, high 3, critical 4). It
  is the team's decision, not the model's, so the queue follows their judgement of
  what matters.

    need  = (uncertainty + chance a check changes the picture) / 2      (0 to 1)
    score = impact × need                                               (0 to 4)

Highest score first; ties go to the most recently started. Every item carries the
reasons in words. The queue also says when the team's assessment differs from the
suggested one and when a check has already been requested, but neither changes the
score: the first is for the analyst to look at, and a pending request does not make an
event less in need of checking.

This is a ranking aid in the sense of value of information (how much a decision could
change if more were known), deliberately simple so that every number can be explained.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.event import Assessment, Event, EventStatus, Priority
from app.models.evidence_request import EvidenceRequest, RequestStatus
from app.services import assess
from app.services import copies as copy_detection

IMPACT = {Priority.LOW: 1, Priority.MEDIUM: 2, Priority.HIGH: 3, Priority.CRITICAL: 4}
OPEN = (EventStatus.ACTIVE, EventStatus.MONITORING)
NEW_REPORTER = "reporter:a-new-field-worker"


def zone(p: float | None) -> str:
    """The side of the assessment's lines a probability falls on."""
    if p is None:
        return "none"
    if p >= assess.HIGH:
        return "yes"
    if p <= assess.LOW:
        return "no"
    return "open"


@dataclass
class CheckValue:
    probability: float | None  # now; None without evidence
    if_supported: float  # after one more field report saying it is happening
    if_denied: float  # ... saying it is not
    chance_supported: float  # how likely that answer is, given what is known now
    changes: float  # chance the answer moves it across a line
    uncertainty: float


def check_value(weights: assess.Weights, vs: list[assess.Vote]) -> CheckValue:
    def new(vote: int) -> assess.Vote:
        relation = (
            assess.EvidenceRelation.SUPPORTS if vote > 0 else assess.EvidenceRelation.CONTRADICTS
        )
        return assess.Vote(NEW_REPORTER, "field", "A field worker", vote, relation, (),
                           datetime.now(UTC))  # fmt: skip

    support, deny = new(1), new(-1)
    r = weights.rate(support)[0]
    p = weights.probability(vs) if vs else None
    plus = weights.probability([*vs, support])
    minus = weights.probability([*vs, deny])
    if p is None:
        # Nothing to go on: any report changes the picture; either answer as likely as
        # the model's starting point says.
        chance = 0.5
        changes = 1.0
        uncertainty = 1.0
    else:
        chance = p * r + (1 - p) * (1 - r)
        now = zone(p)
        changes = chance * (zone(plus) != now) + (1 - chance) * (zone(minus) != now)
        uncertainty = 1 - abs(2 * p - 1)
    return CheckValue(p, plus, minus, chance, changes, uncertainty)


@dataclass
class QueueItem:
    event: Event
    suggested: Assessment
    value: CheckValue
    impact: int
    need: float
    score: float
    reasons: list[str] = field(default_factory=list)
    open_request: EvidenceRequest | None = None
    last_evidence_at: datetime | None = None

    @property
    def differs(self) -> bool:
        """Unverified and insufficient evidence both mean "not decided yet": a new event
        starts as unverified, which is not a disagreement."""
        undecided = {Assessment.UNVERIFIED, Assessment.INSUFFICIENT_EVIDENCE}
        if self.event.assessment in undecided and self.suggested in undecided:
            return False
        return self.event.assessment != self.suggested


def _pct(p: float) -> str:
    if p >= 0.995:
        return ">99%"
    if p <= 0.005:
        return "<1%"
    return f"{round(p * 100)}%"


def _reasons(item: QueueItem) -> list[str]:
    v, e = item.value, item.event
    out = [f"Priority {e.priority.value}, set by the team."]
    if v.probability is None:
        out.append("No evidence linked yet: one field report would change the picture.")
    else:
        out.append(f"{_pct(v.probability)} likely it happened.")
        out.append(
            f"One more field report would move it to {_pct(v.if_supported)} if it says it "
            f"is happening, or {_pct(v.if_denied)} if it says it is not."
        )
        if v.changes >= 0.995:
            out.append("Either answer would change the assessment.")
        elif v.changes > 0:
            out.append(f"A {_pct(v.changes)} chance that a check changes the assessment.")
        else:
            out.append("One report alone would not change the assessment.")
    if item.differs:
        out.append(
            f"The team's assessment ({e.assessment.value.replace('_', ' ')}) differs from "
            f"the suggested one ({item.suggested.value.replace('_', ' ')})."
        )
    if item.open_request is not None:
        n = len(item.open_request.responses)
        out.append(f"A check was requested; {n} {'answer' if n == 1 else 'answers'} so far.")
    return out


def assess_event(
    db: Session, event: Event, weights: assess.Weights, request: EvidenceRequest | None = None
) -> QueueItem:
    found = copy_detection.resolved(db, event)
    vs = assess.votes(event, copy_detection.counted_once(found))
    value = check_value(weights, vs)
    label, _ = assess.label_for(value.probability, vs, weights)
    impact = IMPACT[event.priority]
    need = (value.uncertainty + value.changes) / 2
    item = QueueItem(
        event=event,
        suggested=label,
        value=value,
        impact=impact,
        need=round(need, 4),
        score=round(impact * need, 4),
        open_request=request,
        last_evidence_at=max((v.at for v in vs), default=None),
    )
    item.reasons = _reasons(item)
    return item


def queue(db: Session, *, limit: int = 50) -> tuple[list[QueueItem], int]:
    """Open events, most in need of a check first, and how many open events there are."""
    weights, _ = assess.current_weights(db)
    events = db.scalars(select(Event).where(Event.status.in_(OPEN))).unique().all()
    requests = {
        r.event_id: r
        for r in db.scalars(
            select(EvidenceRequest).where(EvidenceRequest.status == RequestStatus.OPEN)
        ).all()
    }
    items = [assess_event(db, e, weights, requests.get(e.id)) for e in events]
    items.sort(key=lambda i: (-i.score, -i.event.started_at.timestamp(), str(i.event.id)))
    return items[:limit], len(items)


def for_event(db: Session, event_id: uuid.UUID) -> QueueItem | None:
    event = db.get(Event, event_id)
    if event is None:
        return None
    weights, _ = assess.current_weights(db)
    request = db.scalar(
        select(EvidenceRequest).where(
            EvidenceRequest.event_id == event_id, EvidenceRequest.status == RequestStatus.OPEN
        )
    )
    return assess_event(db, event, weights, request)
