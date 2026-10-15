"""Assessment suggestions: how likely an event really happened, and which of the six
labels fits, from the evidence analysts have linked to it.

This is the fusion research's proposed model (ai/fusion, `reliability-dep` with the
assessment of `assess.py`), cut down to what the product records:

- **Votes.** Each linked report or signal that supports or partly supports the event
  says it happened (+1); one that contradicts it says it did not (-1). Adjudicated
  (gold) relations are used where they exist. A source counts once per event, with its
  latest item: a field worker's three reports or a feed's repeated bulletins are one
  voice. (The research also detects copies between different sources from wording and
  photos; the product does not do that yet.)
- **Reliability.** Each source's vote is weighted by how often it has been right: its
  log-odds, log(r / (1 - r)). Two modes, and the API says which one produced a
  suggestion:
  - **start**, while no model has been trained: starting assumptions per kind of
    source (field workers 0.80, public records 0.90, news 0.75, other 0.60) and the
    weighted sum read directly as log-odds;
  - **model**, once an admin has trained one on events whose outcome is known (ground
    truth recorded): each source's own record, shrunk towards its kind's, and a
    calibration fitted on held-out folds so that "80 %" means about 80 %.
- **Label.** At least 80 %: verified, or partially verified if a credible source
  (reliability at least 0.5) partly supports it with a detail marked wrong; at most
  20 %: refuted; in between: conflicting when credible sources say both, otherwise
  unverified; no votes: insufficient evidence.

Suggestions only suggest; an analyst decides. When an analyst changes an event's
assessment, the suggestion at that moment is written to the audit log with whether it
was followed, and the dataset export says the label was made with it in view.
"""

import hashlib
import math
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.extraction import Claim
from app.models.assessment import AssessmentModel
from app.models.event import Assessment, Event, EventEvidence, EvidenceRelation
from app.models.user import User
from app.services import audit, details

STARTING_RATES = {"field": 0.80, "public_record": 0.90, "news": 0.75, "other": 0.60}
DEFAULT_RATE = 0.60
HIGH, LOW = 0.80, 0.20
CREDIBLE = 0.50
STRENGTH = 3.0  # how many of its own items before a source's record outweighs its kind's
TYPE_PRIOR = 2.0  # same, for a kind of source against the starting assumption
RATE_RANGE = (0.05, 0.98)
MIN_EVENTS = 10  # resolved events needed to train
MIN_EACH = 3  # ... including this many that happened and this many that did not
FOLDS = 5
REASONS = 5  # sources shown with a suggestion
VERSION = 1

VOTE = {
    EvidenceRelation.SUPPORTS: 1,
    EvidenceRelation.PARTIALLY_SUPPORTS: 1,
    EvidenceRelation.CONTRADICTS: -1,
}


class NotEnoughDataError(Exception):
    def __init__(self, events: int, happened: int):
        super().__init__(
            f"Training needs at least {MIN_EVENTS} events with ground truth and linked "
            f"evidence, at least {MIN_EACH} that happened and {MIN_EACH} that did not; "
            f"there are {events}, of which {happened} happened."
        )


# --- Evidence as votes ---------------------------------------------------------------------


@dataclass(frozen=True)
class Vote:
    source_key: str
    source_type: str
    source_name: str
    vote: int
    relation: EvidenceRelation
    conflicts: tuple[str, ...]
    at: datetime
    details: tuple[Claim, ...] = ()  # comparable details its text states


def _vote(link: EventEvidence) -> Vote | None:
    relation = link.gold_relation or link.relation
    if relation not in VOTE:
        return None
    conflicts = link.gold_conflicts if link.gold_relation is not None else link.conflicts
    if link.field_report is not None:
        r = link.field_report
        key, kind = f"reporter:{r.reporter_id}", "field"
        name = f"Field worker {r.reporter.full_name}" if r.reporter else "Field worker"
        at = r.received_at
        stated = details.for_report(r)
    else:
        s = link.signal
        key, kind, name, at = (
            f"source:{s.source_id}",
            s.source.source_type.value,
            s.source.name,
            (s.published_at),
        )
        stated = details.for_signal(s)
    comparable = tuple(c for c in stated if c.attribute in details.COMPARABLE)
    return Vote(key, kind, name, VOTE[relation], relation, tuple(conflicts or ()), at, comparable)


def votes(event: Event, copies: frozenset | set = frozenset()) -> list[Vote]:
    """One vote per source: its latest item about the event. Items in `copies` repeat
    an earlier item from another source and are counted through it, not again."""
    latest: dict[str, Vote] = {}
    for link in event.evidence:
        if link.id in copies:
            continue
        v = _vote(link)
        if v is not None and (v.source_key not in latest or v.at >= latest[v.source_key].at):
            latest[v.source_key] = v
    return sorted(latest.values(), key=lambda v: v.at)


# --- Reliability -----------------------------------------------------------------------------


def _clamp(r: float) -> float:
    return min(max(r, RATE_RANGE[0]), RATE_RANGE[1])


def _logit(r: float) -> float:
    r = _clamp(r)
    return math.log(r / (1 - r))


def _sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-max(-50.0, min(50.0, z))))


@dataclass
class Weights:
    rates: dict[str, float] = field(default_factory=dict)
    type_rates: dict[str, float] = field(default_factory=dict)
    calibration: dict[str, float] | None = None

    def rate(self, v: Vote) -> tuple[float, bool]:
        """A source's reliability, and whether it was learned from its own record."""
        if v.source_key in self.rates:
            return self.rates[v.source_key], True
        start = STARTING_RATES.get(v.source_type, DEFAULT_RATE)
        return self.type_rates.get(v.source_type, start), False

    def score(self, vs: list[Vote]) -> float:
        return sum(v.vote * _logit(self.rate(v)[0]) for v in vs)

    def probability(self, vs: list[Vote]) -> float:
        s = self.score(vs)
        if self.calibration is None:
            return _sigmoid(s)
        return _sigmoid(self.calibration["a"] * s + self.calibration["b"])

    def as_json(self) -> dict:
        return {
            "version": VERSION,
            "rates": self.rates,
            "type_rates": self.type_rates,
            "calibration": self.calibration,
        }

    @classmethod
    def from_json(cls, data: dict) -> "Weights":
        if data.get("version") != VERSION:
            raise ValueError("stored assessment model has an older format; retrain it")
        return cls(dict(data["rates"]), dict(data["type_rates"]), data.get("calibration"))


STARTING = Weights()


def learn_rates(resolved: list[tuple[list[Vote], bool]]) -> Weights:
    """Reliability per source and per kind of source from events whose outcome is known:
    the share of a source's votes that matched what happened, shrunk towards its kind's
    share (and that towards the starting assumption)."""
    by_source: dict[str, list[int]] = defaultdict(list)
    by_type: dict[str, list[int]] = defaultdict(list)
    type_of: dict[str, str] = {}
    for vs, happened in resolved:
        truth = 1 if happened else -1
        for v in vs:
            ok = int(v.vote == truth)
            by_source[v.source_key].append(ok)
            by_type[v.source_type].append(ok)
            type_of[v.source_key] = v.source_type
    type_rates = {
        t: _clamp(
            (sum(a) + TYPE_PRIOR * STARTING_RATES.get(t, DEFAULT_RATE)) / (len(a) + TYPE_PRIOR)
        )
        for t, a in by_type.items()
    }
    rates = {
        s: _clamp((sum(a) + STRENGTH * type_rates[type_of[s]]) / (len(a) + STRENGTH))
        for s, a in by_source.items()
    }
    return Weights(rates, type_rates)


def fit_platt(scores: np.ndarray, y: np.ndarray, l2: float = 0.01) -> dict[str, float] | None:
    """p = sigmoid(a * score + b), fitted by Newton's method with a little L2 on a."""
    if len(set(y.tolist())) < 2:
        return None
    x = np.column_stack([scores, np.ones(len(scores))])
    beta = np.array([1.0, 0.0])
    reg = np.array([l2, 0.0])
    for _ in range(100):
        p = 1 / (1 + np.exp(-np.clip(x @ beta, -50, 50)))
        grad = x.T @ (p - y) + reg * (beta - np.array([1.0, 0.0]))
        hess = (x * (p * (1 - p))[:, None]).T @ x + np.diag(reg + 1e-9)
        step = np.linalg.solve(hess, grad)
        beta -= step
        if np.abs(step).max() < 1e-9:
            break
    return {"a": float(beta[0]), "b": float(beta[1])}


def fit(resolved: list[tuple[list[Vote], bool]]) -> Weights:
    """Reliabilities from every resolved event; calibration from out-of-fold scores, so
    it is fitted on scores the reliabilities did not see the outcome of."""
    weights = learn_rates(resolved)
    oof_scores, oof_y = [], []
    k = min(FOLDS, len(resolved))
    for f in range(k):
        train = [r for i, r in enumerate(resolved) if i % k != f]
        test = [r for i, r in enumerate(resolved) if i % k == f]
        fold = learn_rates(train)
        for vs, happened in test:
            oof_scores.append(fold.score(vs))
            oof_y.append(int(happened))
    weights.calibration = fit_platt(np.array(oof_scores), np.array(oof_y))
    return weights


# --- Suggestion --------------------------------------------------------------------------


@dataclass
class Stated:
    """One source's value for a detail."""

    value: object
    unit: str | None
    source: str
    reliability: float
    surface: str


@dataclass
class DetailSummary:
    """What the supporting sources say about one detail, and the best estimate."""

    attribute: str
    estimate: object
    unit: str | None
    disputed: bool
    statements: list[Stated]


@dataclass
class Reason:
    source: str
    kind: str
    vote: int
    reliability: float
    learned: bool
    disputed: tuple[str, ...]


@dataclass
class AssessmentSuggestion:
    label: Assessment
    probability: float | None
    method: str  # "start" or "model"
    model_id: uuid.UUID | None
    sources_supporting: int
    sources_denying: int
    credible_supporting: int
    credible_denying: int
    disputed: list[str]
    reasons: list[Reason]
    disputed_detected: list[str] = field(default_factory=list)
    details: list[DetailSummary] = field(default_factory=list)
    counted_once: int = 0  # items that repeat another source's, not counted again


def _weight(rate: float) -> float:
    return max(_logit(rate), 0.01)


def _estimate(attribute: str, stated: list[tuple[Claim, float]]):
    """Weighted median for counts, weighted mode otherwise ("unknown" only if nothing
    else is stated), each source weighted by the log-odds of its reliability."""
    known = [(c, r) for c, r in stated if c.value != "unknown"] or stated
    if attribute in ("affected_count", "casualty_count"):
        pairs = sorted((float(c.value), _weight(r)) for c, r in known)
        half, acc = sum(w for _, w in pairs) / 2, 0.0
        for value, w in pairs:
            acc += w
            if acc >= half:
                return int(value) if value.is_integer() else value
        return pairs[-1][0]
    totals: dict = defaultdict(float)
    for c, r in known:
        totals[c.value] += _weight(r)
    return max(totals, key=lambda v: totals[v])


def summarise_details(vs: list[Vote], weights: Weights) -> tuple[list[DetailSummary], list[str]]:
    """Per detail the supporting sources state: every statement, the best estimate,
    and whether two credible sources disagree (a detected dispute)."""
    by_attribute: dict[str, list[tuple[Claim, float, Vote]]] = defaultdict(list)
    for v in vs:
        if v.vote < 0:
            continue
        rate = weights.rate(v)[0]
        for c in v.details:
            by_attribute[c.attribute].append((c, rate, v))
    summaries, detected = [], []
    for attribute in details.COMPARABLE:
        stated = by_attribute.get(attribute)
        if not stated:
            continue
        credible = [c for c, r, _ in stated if r >= CREDIBLE]
        disputed = any(
            not details.agrees(attribute, a.value, b.value) for a in credible for b in credible
        )
        if disputed:
            detected.append(attribute)
        estimate = _estimate(attribute, [(c, r) for c, r, _ in stated])
        summaries.append(
            DetailSummary(
                attribute=attribute,
                estimate=estimate,
                unit=next((c.unit for c, _, _ in stated if c.value == estimate), None),
                disputed=disputed,
                statements=[
                    Stated(c.value, c.unit, v.source_name, round(r, 3), c.surface)
                    for c, r, v in sorted(stated, key=lambda x: -x[1])
                ],
            )
        )
    return summaries, detected


def label_for(
    p: float | None, vs: list[Vote], weights: Weights, detected: list[str] = ()
) -> tuple[Assessment, list[str]]:
    """The label, and the details in dispute: marked wrong by an analyst on a credible
    source's link, or stated differently by two credible sources (`detected`)."""
    if not vs or p is None:
        return Assessment.INSUFFICIENT_EVIDENCE, []
    credible = [v for v in vs if weights.rate(v)[0] >= CREDIBLE]
    marked = {
        c
        for v in credible
        if v.relation == EvidenceRelation.PARTIALLY_SUPPORTS
        for c in v.conflicts
        if c != "occurrence"
    }
    disputed = sorted(marked | set(detected))
    if p >= HIGH:
        return (Assessment.PARTIALLY_VERIFIED if disputed else Assessment.VERIFIED), disputed
    if p <= LOW:
        return Assessment.REFUTED, disputed
    both = any(v.vote > 0 for v in credible) and any(v.vote < 0 for v in credible)
    return (Assessment.CONFLICTING if both else Assessment.UNVERIFIED), disputed


def active_model(db: Session) -> AssessmentModel | None:
    return db.scalars(select(AssessmentModel).where(AssessmentModel.active.is_(True))).first()


def current_weights(db: Session) -> tuple[Weights, AssessmentModel | None]:
    model = active_model(db)
    if model is None:
        return STARTING, None
    try:
        return Weights.from_json(model.weights), model
    except (ValueError, KeyError):
        return STARTING, None


def suggest(db: Session, event: Event) -> AssessmentSuggestion:
    from app.services import copies as copy_detection

    weights, model = current_weights(db)
    found = copy_detection.resolved(db, event)
    vs = votes(event, copy_detection.counted_once(found))
    p = weights.probability(vs) if vs else None
    summaries, detected = summarise_details(vs, weights)
    label, disputed = label_for(p, vs, weights, detected)
    rated = [(v, *weights.rate(v)) for v in vs]
    credible = [(v, r) for v, r, _ in rated if r >= CREDIBLE]
    rated.sort(key=lambda x: abs(_logit(x[1])), reverse=True)
    return AssessmentSuggestion(
        label=label,
        probability=p,
        method="model" if model else "start",
        model_id=model.id if model else None,
        sources_supporting=sum(v.vote > 0 for v in vs),
        sources_denying=sum(v.vote < 0 for v in vs),
        credible_supporting=sum(v.vote > 0 for v, _ in credible),
        credible_denying=sum(v.vote < 0 for v, _ in credible),
        disputed=disputed,
        reasons=[
            Reason(
                source=v.source_name,
                kind=v.source_type,
                vote=v.vote,
                reliability=round(r, 3),
                learned=learned,
                disputed=tuple(c for c in v.conflicts if c != "occurrence")
                if v.relation == EvidenceRelation.PARTIALLY_SUPPORTS
                else (),
            )
            for v, r, learned in rated[:REASONS]
        ],
        disputed_detected=detected,
        details=summaries,
        counted_once=len(copy_detection.counted_once(found)),
    )


def for_audit(s: AssessmentSuggestion, chosen: str) -> dict:
    """What is written to the audit log when an analyst sets an assessment."""
    return {
        "label": s.label.value,
        "probability": round(s.probability, 3) if s.probability is not None else None,
        "method": s.method,
        "model_id": str(s.model_id) if s.model_id else None,
        "followed": s.label.value == chosen,
    }


# --- Training ----------------------------------------------------------------------------


def copied(db: Session, event: Event) -> set:
    """The event's items that are copies (detected or confirmed, not rejected)."""
    from app.services import copies as copy_detection

    return copy_detection.counted_once(copy_detection.resolved(db, event))


def resolved_events(db: Session) -> list[tuple[Event, list[Vote]]]:
    """Events whose outcome is recorded and that have at least one vote."""
    events = db.scalars(select(Event).where(Event.occurred.is_not(None))).all()
    out = []
    for e in events:
        vs = votes(e, copied(db, e))
        if vs:
            out.append((e, vs))
    out.sort(key=lambda x: str(x[0].id))
    return out


def _held_out(event_id: uuid.UUID) -> bool:
    """One event in five, chosen by its id (the same split as event suggestions)."""
    return int(hashlib.sha256(str(event_id).encode()).hexdigest(), 16) % FOLDS == 0


def _brier(ps: list[float], ys: list[int]) -> float:
    return float(np.mean([(p - y) ** 2 for p, y in zip(ps, ys, strict=True)]))


def _accuracy(ps: list[float], ys: list[int]) -> float:
    return float(np.mean([(p >= 0.5) == (y == 1) for p, y in zip(ps, ys, strict=True)]))


def _majority(vs: list[Vote]) -> float:
    return (sum(v.vote > 0 for v in vs) + 1) / (len(vs) + 2)


def evaluate(train: list[tuple[list[Vote], bool]], test: list[tuple[list[Vote], bool]]) -> dict:
    """Held-out comparison: the model fitted on `train`, the starting assumptions, and
    majority vote (share of sources saying it happened), scored on `test`."""
    weights = fit(train)
    ys = [int(h) for _, h in test]
    preds = {
        "model": [weights.probability(vs) for vs, _ in test],
        "start": [STARTING.probability(vs) for vs, _ in test],
        "majority": [_majority(vs) for vs, _ in test],
    }
    out: dict = {"held_out_events": len(test), "held_out_happened": sum(ys)}
    for name, ps in preds.items():
        out[f"{name}_brier"] = round(_brier(ps, ys), 4)
        out[f"{name}_accuracy"] = round(_accuracy(ps, ys), 4)
    return out


def train(db: Session, actor: User | None, ip_address: str | None = None) -> AssessmentModel:
    """Evaluate on held-out events (one in five), then fit on all and make it active."""
    rows = resolved_events(db)
    happened = sum(bool(e.occurred) for e, _ in rows)
    if len(rows) < MIN_EVENTS or happened < MIN_EACH or len(rows) - happened < MIN_EACH:
        raise NotEnoughDataError(len(rows), happened)
    data = [(vs, bool(e.occurred)) for e, vs in rows]
    held = [(vs, bool(e.occurred)) for e, vs in rows if _held_out(e.id)]
    rest = [(vs, bool(e.occurred)) for e, vs in rows if not _held_out(e.id)]
    metrics: dict = {"held_out_events": len(held)}
    if held and len({h for _, h in rest}) == 2:
        metrics = evaluate(rest, held)
    weights = fit(data)

    db.execute(update(AssessmentModel).values(active=False))
    model = AssessmentModel(
        id=uuid.uuid4(),
        created_by_id=actor.id if actor else None,
        active=True,
        events=len(rows),
        happened=happened,
        sources=len(weights.rates),
        weights=weights.as_json(),
        metrics=metrics,
    )
    db.add(model)
    audit.record(
        db,
        audit.AuditAction.ASSESSMENT_TRAINED,
        actor_id=actor.id if actor else None,
        target_type="assessment_model",
        target_id=model.id,
        ip_address=ip_address,
        details={"events": model.events, "happened": happened, **metrics},
    )
    db.commit()
    db.refresh(model)
    return model


def usage(db: Session) -> dict[str, int]:
    """Assessments set with a suggestion in view, from the audit log, and how many
    followed it."""
    from app.models.audit import AuditLog

    rows = db.scalars(
        select(AuditLog.details).where(
            AuditLog.action == audit.AuditAction.EVENT_UPDATED,
            AuditLog.details["suggestion"].is_not(None),
        )
    ).all()
    shown = [d["suggestion"] for d in rows if d.get("suggestion")]
    return {"total": len(shown), "followed": sum(bool(s.get("followed")) for s in shown)}


def status(db: Session) -> dict:
    rows = resolved_events(db)
    happened = sum(bool(e.occurred) for e, _ in rows)
    model = active_model(db)
    return {
        "method": "model" if model else "start",
        "active": model,
        "resolved_events": len(rows),
        "resolved_happened": happened,
        "min_events": MIN_EVENTS,
        "min_each": MIN_EACH,
        "starting_rates": STARTING_RATES,
        "from_suggestions": usage(db),
    }


def deactivate(db: Session, actor: User, ip_address: str | None = None) -> None:
    model = active_model(db)
    if model is None:
        return
    model.active = False
    audit.record(
        db,
        audit.AuditAction.ASSESSMENT_TRAINED,
        actor_id=actor.id,
        target_type="assessment_model",
        target_id=model.id,
        ip_address=ip_address,
        details={"deactivated": True},
    )
    db.commit()
