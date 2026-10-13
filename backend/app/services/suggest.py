"""Event suggestions: which existing events a report or a signal most likely belongs to.

Two modes, and the API says which one produced a list:

- **rule**, while no model has been trained: the transparent 5 km / 48 h rule in
  services/events.py, same type first, then nearest. This is baseline B2 of the
  correlation research (ai/correlation).
- **model**, once an admin has trained one on the links analysts have made: a wider
  search (50 km plus the item's own location uncertainty, and 14 days around the
  event), ranked by a logistic model over the same cluster-level features as the
  research's `cjoint` (ai/correlation/carcux_correlation/cluster_model.py): how similar
  the wording is to the event's evidence, how far in time from it, how far in space,
  whether the type agrees, how big the event is. On the public news benchmark this
  design beat text alone and matched or beat the rule; here it is measured on each
  instance's own data at every training run, against the rule, on held-out events.

One difference from the research model: analysts often work through a backlog, so an
item can be older than an event's newest evidence. Time is measured to the event's
evidence span (zero inside it), not only forward from the newest item.

Suggestions only rank; an analyst decides. When an analyst links from a suggestion,
its rank, score and model are written to the audit log, so how often the first
suggestion was right can be measured in real use.
"""

import hashlib
import math
import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.event_types import EVENT_TYPE_FAMILY
from app.models.event import ABOUT_THE_EVENT, Event, EventEvidence, EventStatus, EvidenceRelation
from app.models.field_report import FieldReport
from app.models.signal import Signal
from app.models.suggestion import SuggestionModel
from app.models.user import User
from app.services import audit
from app.services import events as rules
from app.services.integrity import haversine_km

RADIUS_KM = 50.0
MAX_REACH_KM = 300.0
WINDOW = timedelta(days=14)
MAX_CANDIDATES = 200  # events scored per item (most recent first)
MAX_MEMBERS = 60  # most recent evidence per event used for its features
LIMIT = 10  # suggestions returned
MIN_SCORE = 0.05  # below this the model thinks it is not the same situation: not shown
MIN_ITEMS = 20  # labelled items needed to train
MIN_EVENTS = 5
HELD_OUT_SHARE = 5  # one event in five is held out for evaluation

NAMES = [
    "centroid_cos",
    "max_cos",
    "log_hours_newest",
    "log_hours_oldest",
    "log_size",
    "any_located",
    "log_min_km",
    "log_min_scaled_km",
    "same_type_share",
    "type_unknown",
    "cos_x_recency",
    "log_gap_ratio",
]
NC = {name: k for k, name in enumerate(NAMES)}


class NotEnoughDataError(Exception):
    def __init__(self, items: int, events: int):
        super().__init__(
            f"Training needs at least {MIN_ITEMS} linked reports or signals across "
            f"{MIN_EVENTS} events; there are {items} across {events}."
        )
        self.items, self.events = items, events


# --- What the features see -------------------------------------------------------------


@dataclass(frozen=True)
class Item:
    """A report, a signal, or an event's own record, reduced to what the features use."""

    key: str  # "report:<id>", "signal:<id>" or "event:<id>"
    text: str
    time: datetime
    lat: float | None
    lon: float | None
    precision_km: float
    event_type: str | None

    @property
    def located(self) -> bool:
        return self.lat is not None and self.lon is not None


def from_report(r: FieldReport) -> Item:
    return Item(
        key=f"report:{r.id}",
        text=" ".join(filter(None, [r.text, r.place_name])),
        time=r.observed_at,
        lat=r.latitude,
        lon=r.longitude,
        precision_km=(r.location_accuracy_m or 0) / 1000,
        event_type=r.event_type,
    )


def from_signal(s: Signal) -> Item:
    return Item(
        key=f"signal:{s.id}",
        text=" ".join(filter(None, [s.title, s.text, s.place_name])),
        time=s.valid_from or s.published_at,
        lat=s.latitude,
        lon=s.longitude,
        precision_km=min((s.precision_m or 0) / 1000, MAX_REACH_KM),
        event_type=s.event_type,
    )


def from_event(e: Event) -> Item:
    return Item(
        key=f"event:{e.id}",
        text=" ".join(filter(None, [e.title, e.summary, e.place_name])),
        time=e.started_at,
        lat=e.latitude,
        lon=e.longitude,
        precision_km=0.0,
        event_type=e.event_type,
    )


def _effective(link: EventEvidence) -> EvidenceRelation:
    return link.gold_relation or link.relation


def members(event: Event, *, exclude: str | None = None) -> list[Item]:
    """The event's own record plus the most recent evidence that is about it."""
    evidence = []
    for link in event.evidence:
        if _effective(link) not in ABOUT_THE_EVENT:
            continue
        item = from_report(link.field_report) if link.field_report else from_signal(link.signal)
        if item.key != exclude:
            evidence.append(item)
    evidence.sort(key=lambda i: i.time, reverse=True)
    return [from_event(event), *evidence[:MAX_MEMBERS]]


# --- Text ---------------------------------------------------------------------------------

_SPLIT = re.compile(r"[\s.,;:!?'\"()\[\]{}।/\\|–—\-]+")


def _grams(text: str) -> Counter:
    """Character 2- to 4-grams inside words, as in the research (`char_wb`): works for
    Bangla script, Banglish and English without a tokenizer."""
    out: Counter = Counter()
    for word in _SPLIT.split(text.lower()):
        if not word:
            continue
        padded = f" {word} "
        for n in (2, 3, 4):
            for k in range(len(padded) - n + 1):
                out[padded[k : k + n]] += 1
    return out


class TextSpace:
    """TF-IDF (sublinear) fitted on the texts being compared, L2-normalised."""

    def __init__(self, texts: list[str]):
        self.counts = [_grams(t) for t in texts]
        df: Counter = Counter()
        for c in self.counts:
            df.update(c.keys())
        n = len(texts)
        self.idf = {g: math.log((1 + n) / (1 + d)) + 1 for g, d in df.items()}
        self.vectors = [self._vector(c) for c in self.counts]

    def _vector(self, counts: Counter) -> dict[str, float]:
        v = {g: (1 + math.log(c)) * self.idf[g] for g, c in counts.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {g: x / norm for g, x in v.items()}

    @staticmethod
    def dot(a: dict[str, float], b: dict[str, float]) -> float:
        if len(a) > len(b):
            a, b = b, a
        return sum(x * b.get(g, 0.0) for g, x in a.items())


# --- Features -----------------------------------------------------------------------------


def _hours(a: datetime, b: datetime) -> float:
    return (a - b).total_seconds() / 3600


def features(item: Item, groups: list[list[Item]]) -> np.ndarray:
    """One row per candidate event (`groups[k]` are its members)."""
    texts = [item.text] + [m.text for g in groups for m in g]
    space = TextSpace(texts)
    q = space.vectors[0]
    out = np.zeros((len(groups), len(NAMES)))
    pos = 1
    for k, group in enumerate(groups):
        vecs = space.vectors[pos : pos + len(group)]
        pos += len(group)
        cos = [space.dot(q, v) for v in vecs]
        total: dict[str, float] = {}
        for v in vecs:
            for g, x in v.items():
                total[g] = total.get(g, 0.0) + x
        norm = math.sqrt(sum(x * x for x in total.values())) or 1.0
        centroid = space.dot(q, total) / norm
        times = [m.time for m in group]
        newest, oldest = max(times), min(times)
        if item.time > newest:
            gap = _hours(item.time, newest)
        elif item.time < oldest:
            gap = _hours(oldest, item.time)
        else:
            gap = 0.0
        age = abs(_hours(item.time, oldest))
        mean_gap = _hours(newest, oldest) / max(len(group) - 1, 1)
        row = out[k]
        row[NC["centroid_cos"]] = centroid
        row[NC["max_cos"]] = max(cos)
        row[NC["log_hours_newest"]] = math.log1p(gap)
        row[NC["log_hours_oldest"]] = math.log1p(age)
        row[NC["log_size"]] = math.log(len(group))
        located = [m for m in group if m.located] if item.located else []
        if located:
            km = [haversine_km(item.lat, item.lon, m.lat, m.lon) for m in located]
            spread = [1 + item.precision_km + m.precision_km for m in located]
            scaled = [d / w for d, w in zip(km, spread, strict=True)]
            row[NC["any_located"]] = 1.0
            row[NC["log_min_km"]] = math.log1p(min(km))
            row[NC["log_min_scaled_km"]] = math.log1p(min(scaled))
        typed = [m for m in group if m.event_type] if item.event_type else []
        if typed:
            row[NC["same_type_share"]] = sum(m.event_type == item.event_type for m in typed) / len(
                typed
            )
        else:
            row[NC["type_unknown"]] = 1.0
        row[NC["cos_x_recency"]] = centroid * math.log1p(gap)
        row[NC["log_gap_ratio"]] = math.log1p(gap / (mean_gap + 1.0))
    return out


# --- Model --------------------------------------------------------------------------------


def fit_logistic(x: np.ndarray, y: np.ndarray, C: float = 1.0) -> dict:
    """L2-regularised logistic regression on standardised features, classes balanced,
    fitted by Newton's method. Returns weights in the stored form."""
    mean = x.mean(axis=0)
    scale = x.std(axis=0)
    scale[scale == 0] = 1.0
    z = (x - mean) / scale
    n, d = z.shape
    pos = max(int(y.sum()), 1)
    neg = max(n - pos, 1)
    w_sample = np.where(y == 1, n / (2 * pos), n / (2 * neg))
    a = np.hstack([z, np.ones((n, 1))])
    beta = np.zeros(d + 1)
    reg = np.r_[np.full(d, 1.0 / C), 0.0]  # intercept not penalised
    for _ in range(50):
        p = 1 / (1 + np.exp(-np.clip(a @ beta, -50, 50)))
        grad = a.T @ (w_sample * (p - y)) + reg * beta
        hess = (a * (w_sample * p * (1 - p))[:, None]).T @ a + np.diag(reg + 1e-9)
        step = np.linalg.solve(hess, grad)
        beta -= step
        if np.abs(step).max() < 1e-8:
            break
    return {
        "names": NAMES,
        "mean": mean.tolist(),
        "scale": scale.tolist(),
        "coef": beta[:d].tolist(),
        "intercept": float(beta[d]),
    }


def probability(weights: dict, x: np.ndarray) -> np.ndarray:
    if weights.get("names") != NAMES:
        raise ValueError("stored model has different features; retrain it")
    z = (x - np.array(weights["mean"])) / np.array(weights["scale"])
    return 1 / (1 + np.exp(-np.clip(z @ np.array(weights["coef"]) + weights["intercept"], -50, 50)))


# --- Retrieval ----------------------------------------------------------------------------


def retrieve(db: Session, item: Item, *, exclude: set[uuid.UUID] = frozenset()) -> list[Event]:
    """Events worth scoring: not dismissed, within 14 days of the item, and within 50 km
    plus the item's uncertainty (any distance when the item has no location)."""
    now = datetime.now(UTC)
    q = select(Event).where(
        Event.status != EventStatus.DISMISSED,
        Event.started_at <= item.time + WINDOW,
        func.coalesce(Event.ended_at, now) >= item.time - WINDOW,
    )
    if exclude:
        q = q.where(Event.id.not_in(exclude))
    reach = RADIUS_KM + item.precision_km
    if item.located:
        dlat, dlon = rules._bbox(item.lat, item.lon, reach)
        q = q.where(
            Event.latitude.between(item.lat - dlat, item.lat + dlat),
            Event.longitude.between(item.lon - dlon, item.lon + dlon),
        )
    found = db.scalars(q.order_by(Event.started_at.desc()).limit(MAX_CANDIDATES)).all()
    if item.located:
        found = [
            e for e in found if haversine_km(item.lat, item.lon, e.latitude, e.longitude) <= reach
        ]
    return list(found)


def rule_rank(item: Item, events: list[Event]) -> list[Event]:
    """The 5 km / 48 h rule (services/events.py) applied to a candidate list."""
    if not item.located:
        return []
    now = datetime.now(UTC)
    reach = rules.MATCH_RADIUS_KM + item.precision_km
    kept = []
    for e in events:
        km = haversine_km(item.lat, item.lon, e.latitude, e.longitude)
        hours = rules._hours_outside(item.time, e.started_at, e.ended_at or now)
        if km <= reach and hours <= rules.MATCH_WINDOW.total_seconds() / 3600:
            kept.append((e.event_type != item.event_type, km, e))
    return [e for *_, e in sorted(kept, key=lambda t: (t[0], t[1]))]


# --- Suggestions --------------------------------------------------------------------------


@dataclass
class Suggestion:
    event: Event
    distance_km: float | None  # None when the item has no location
    hours_apart: float
    same_type: bool
    same_family: bool
    method: str  # "model" or "rule"
    score: float | None = None
    text_similarity: float | None = None
    hours_from_latest: float | None = None  # item time minus the event's newest evidence
    model_id: uuid.UUID | None = None


def active_model(db: Session) -> SuggestionModel | None:
    return db.scalar(select(SuggestionModel).where(SuggestionModel.active.is_(True)))


def _display(item: Item, event: Event) -> tuple[float | None, float, bool, bool]:
    now = datetime.now(UTC)
    km = haversine_km(item.lat, item.lon, event.latitude, event.longitude) if item.located else None
    hours = rules._hours_outside(item.time, event.started_at, event.ended_at or now)
    family = EVENT_TYPE_FAMILY.get(item.event_type or "")
    return (
        round(km, 2) if km is not None else None,
        round(hours, 1),
        event.event_type == item.event_type,
        family is not None and event.family == family,
    )


def suggest(db: Session, item: Item, linked: set[uuid.UUID]) -> list[Suggestion]:
    """Ranked events for one item, excluding events it is already linked to."""
    model = active_model(db)
    if model is None:
        return []  # callers use the rule (services/events.py) directly
    events = retrieve(db, item, exclude=linked)
    if not events:
        return []
    groups = [members(e, exclude=item.key) for e in events]
    x = features(item, groups)
    p = probability(model.weights, x)
    order = [k for k in np.argsort(-p, kind="stable") if p[k] >= MIN_SCORE][:LIMIT]
    out = []
    for k in order:
        e = events[k]
        km, hours, same_type, same_family = _display(item, e)
        newest = max(m.time for m in groups[k])
        out.append(
            Suggestion(
                event=e,
                distance_km=km,
                hours_apart=hours,
                same_type=same_type,
                same_family=same_family,
                method="model",
                score=round(float(p[k]), 3),
                text_similarity=round(float(x[k, NC["centroid_cos"]]), 3),
                hours_from_latest=round(_hours(item.time, newest), 1),
                model_id=model.id,
            )
        )
    return out


# --- Training -----------------------------------------------------------------------------


@dataclass
class _Labelled:
    item: Item
    positives: set[uuid.UUID] = field(default_factory=set)
    negatives: set[uuid.UUID] = field(default_factory=set)  # labelled unrelated


def labelled_items(db: Session) -> list[_Labelled]:
    """Every report and signal analysts have linked, with the events it is about and the
    events it was marked unrelated to (gold label where adjudicated)."""
    by_key: dict[str, _Labelled] = {}
    for link in db.scalars(select(EventEvidence)).all():
        item = from_report(link.field_report) if link.field_report else from_signal(link.signal)
        entry = by_key.setdefault(item.key, _Labelled(item))
        if _effective(link) in ABOUT_THE_EVENT:
            entry.positives.add(link.event_id)
        else:
            entry.negatives.add(link.event_id)
    return [e for e in by_key.values() if e.positives]


def _held_out(event_id: uuid.UUID) -> bool:
    return int(hashlib.sha256(str(event_id).encode()).hexdigest(), 16) % HELD_OUT_SHARE == 0


def _rows(db: Session, entry: _Labelled, events_by_id: dict[uuid.UUID, Event]):
    """Training rows for one item: every retrieved event plus its labelled ones."""
    retrieved = retrieve(db, entry.item)
    ids = {e.id for e in retrieved}
    extra = [
        events_by_id[i] for i in (entry.positives | entry.negatives) - ids if i in events_by_id
    ]
    events = retrieved + extra
    groups = [members(e, exclude=entry.item.key) for e in events]
    x = features(entry.item, groups)
    y = np.array([int(e.id in entry.positives) for e in events])
    return events, retrieved, x, y


def train(db: Session, actor: User | None, ip_address: str | None = None) -> SuggestionModel:
    """Fit a model on the links analysts have made, evaluate it on held-out events
    against the rule, then refit on everything and make it the active model."""
    entries = labelled_items(db)
    all_events = {e for entry in entries for e in entry.positives}
    if len(entries) < MIN_ITEMS or len(all_events) < MIN_EVENTS:
        raise NotEnoughDataError(len(entries), len(all_events))
    events_by_id = {e.id: e for e in db.scalars(select(Event)).all()}

    train_x, train_y, all_x, all_y = [], [], [], []
    evaluation = []  # (entry, retrieved events, x of retrieved)
    for entry in entries:
        events, retrieved, x, y = _rows(db, entry, events_by_id)
        all_x.append(x)
        all_y.append(y)
        if any(_held_out(e) for e in entry.positives):
            evaluation.append((entry, retrieved, x[: len(retrieved)]))
        else:
            train_x.append(x)
            train_y.append(y)

    metrics: dict = {"held_out_items": len(evaluation)}
    if evaluation and train_y and len(set(np.concatenate(train_y).tolist())) == 2:
        held_weights = fit_logistic(np.vstack(train_x), np.concatenate(train_y))
        metrics.update(_evaluate(evaluation, held_weights))
    x, y = np.vstack(all_x), np.concatenate(all_y)
    if len(set(y.tolist())) < 2:
        raise NotEnoughDataError(len(entries), len(all_events))
    weights = fit_logistic(x, y)

    db.execute(update(SuggestionModel).values(active=False))
    model = SuggestionModel(
        id=uuid.uuid4(),
        created_by_id=actor.id if actor else None,
        active=True,
        items=len(entries),
        events=len(all_events),
        positives=int(y.sum()),
        negatives=int(len(y) - y.sum()),
        weights=weights,
        metrics=metrics,
    )
    db.add(model)
    audit.record(
        db,
        audit.AuditAction.SUGGESTIONS_TRAINED,
        actor_id=actor.id if actor else None,
        target_type="suggestion_model",
        target_id=model.id,
        ip_address=ip_address,
        details={"items": model.items, "events": model.events, **metrics},
    )
    db.commit()
    db.refresh(model)
    return model


def _evaluate(evaluation, weights: dict) -> dict:
    """Top-1 and top-3: is an event the item is about ranked first (in the first three)?
    The rule ranks the same retrieved events with its own filter and order."""
    hits = {"model_top1": 0, "model_top3": 0, "rule_top1": 0, "rule_top3": 0, "retrieved": 0}
    events_seen = set()
    for entry, retrieved, x in evaluation:
        events_seen |= entry.positives
        if any(e.id in entry.positives for e in retrieved):
            hits["retrieved"] += 1
        if retrieved:
            p = probability(weights, x)
            ranked = [retrieved[k] for k in np.argsort(-p, kind="stable")]
            hits["model_top1"] += ranked[0].id in entry.positives
            hits["model_top3"] += any(e.id in entry.positives for e in ranked[:3])
        by_rule = rule_rank(entry.item, retrieved)
        hits["rule_top1"] += bool(by_rule) and by_rule[0].id in entry.positives
        hits["rule_top3"] += any(e.id in entry.positives for e in by_rule[:3])
    n = len(evaluation)
    return {
        "held_out_events": len(events_seen),
        **{k: round(v / n, 3) for k, v in hits.items()},
    }


# --- Entry points for the API -------------------------------------------------------------


def _linked(db: Session, column, item_id: uuid.UUID) -> set[uuid.UUID]:
    return set(db.scalars(select(EventEvidence.event_id).where(column == item_id)).all())


def _from_rule(item: Item, matches) -> list[Suggestion]:
    family = EVENT_TYPE_FAMILY.get(item.event_type or "")
    return [
        Suggestion(
            event=event,
            distance_km=m.distance_km,
            hours_apart=m.hours_apart,
            same_type=event.event_type == item.event_type,
            same_family=family is not None and event.family == family,
            method="rule",
        )
        for event, m in matches
    ]


def for_report(db: Session, report: FieldReport) -> list[Suggestion]:
    item = from_report(report)
    if active_model(db) is None:
        return _from_rule(item, rules.candidate_events(db, report))
    return suggest(db, item, _linked(db, EventEvidence.field_report_id, report.id))


def for_signal(db: Session, signal: Signal) -> list[Suggestion]:
    item = from_signal(signal)
    if active_model(db) is None:
        return _from_rule(item, rules.candidate_events_for_signal(db, signal))
    return suggest(db, item, _linked(db, EventEvidence.signal_id, signal.id))


def usage(db: Session) -> dict[str, int]:
    """Links made from a suggestion list, from the audit log: how many, and how many
    took the first suggestion or one of the first three."""
    from app.models.audit import AuditLog

    rows = db.scalars(
        select(AuditLog.details).where(
            AuditLog.action == audit.AuditAction.EVIDENCE_LINKED,
            AuditLog.details["suggestion"].is_not(None),
        )
    ).all()
    ranks = [int(d["suggestion"].get("rank", 0)) for d in rows if d.get("suggestion")]
    return {
        "total": len(ranks),
        "first": sum(r == 1 for r in ranks),
        "top3": sum(1 <= r <= 3 for r in ranks),
    }


def status(db: Session) -> dict:
    entries = labelled_items(db)
    previous = db.scalars(
        select(SuggestionModel)
        .where(SuggestionModel.active.is_(False))
        .order_by(SuggestionModel.created_at.desc())
        .limit(5)
    ).all()
    model = active_model(db)
    return {
        "method": "model" if model else "rule",
        "active": model,
        "previous": list(previous),
        "labelled_items": len(entries),
        "labelled_events": len({e for entry in entries for e in entry.positives}),
        "min_items": MIN_ITEMS,
        "min_events": MIN_EVENTS,
        "from_suggestions": usage(db),
    }


def deactivate(db: Session, actor: User, ip_address: str | None = None) -> None:
    """Go back to the rule."""
    model = active_model(db)
    if model is None:
        return
    model.active = False
    audit.record(
        db,
        audit.AuditAction.SUGGESTIONS_TRAINED,
        actor_id=actor.id,
        target_type="suggestion_model",
        target_id=model.id,
        ip_address=ip_address,
        details={"deactivated": True},
    )
    db.commit()
