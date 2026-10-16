"""Stance suggestions: how a report or signal bears on an event, suggested to the analyst
who links it (supports, partly supports, contradicts, related only, not this event).

Transparent rules, each with its reason, strongest first:

1. **contradicts:** the text denies the event or calls it false, a rumour, fake
   ("eta gujob", "খবরটি গুজব", "the report is false"), as the extraction module reads
   denials;
2. **unrelated** ("not this event"): the item is about another kind of event (its own
   type, or the type its words point to, is in another family than the event's);
3. **partially_supports:** it states a detail (deaths, people affected, depth, cause)
   that disagrees with the estimate from the event's other credible sources ("20 dead"
   where the others say 3), with that detail as the conflict;
4. **related:** it asks or comments ("ki hoise?", "dua koren", "anyone know …") and
   states nothing checkable;
5. **supports** otherwise: it reports the event and nothing in it says otherwise. This
   is the weakest suggestion: the analyst must read the item.

A suggestion only: the analyst labels the link. When an analyst links an item or
changes its relation, the suggestion at that moment and whether it was followed go into
the audit log. Second-opinion annotators never see suggestions (the blind queue does
not show them), so agreement between annotators is not inflated by them.
"""

import re
import uuid
from dataclasses import dataclass, field

from app.core.event_types import EVENT_TYPE_FAMILY
from app.extraction import extract
from app.ingest.classify import classify
from app.models.event import Event, EvidenceRelation
from app.services import details

RELATED_CUES = re.compile(
    r"\bpray(?:ing|ers?)?\b|\bthoughts\b|stay safe|is (?:it|this) true|anyone know|"
    r"any (?:update|news)|what happened|\?\s*$|"
    r"দোয়া|দোয়া|আল্লাহ|নিরাপদে থাকুন|কেউ জানেন|সত্যি নাকি|কী হয়েছে|কি হয়েছে|"
    r"\bdua\b|\bdoa\b|\ballah\b|safe thakben|keu jane[n]?|sotti naki|shotti naki|"
    r"ki hoise|ki hoyeche|ki hoilo",
    re.IGNORECASE,
)


@dataclass
class StanceSuggestion:
    relation: EvidenceRelation
    strength: str  # strong, medium, weak
    reasons: list[str]
    conflicts: list[str] = field(default_factory=list)


def _label(event_type: str) -> str:
    return event_type.replace("_", " ")


def _a(event_type: str) -> str:
    """The event type with its article: "a flood", "an earthquake"."""
    label = _label(event_type)
    return ("an " if label[0] in "aeiou" else "a ") + label


def _value(attribute: str, value, unit: str | None) -> str:
    if attribute == "casualty_count":
        return f"{value} dead"
    if attribute == "affected_count":
        return f"{value} {unit or 'people'} affected"
    return str(value)


def suggest(
    db,
    event: Event,
    text: str,
    *,
    item_type: str | None = None,
    exclude: uuid.UUID | None = None,
) -> StanceSuggestion:
    """The suggested relation of `text` to `event`; `exclude` is the item's own link
    when it is already linked, so it is not compared with itself."""
    claims = extract(text)
    denial = next((c for c in claims if c.attribute == "occurrence" and c.value is False), None)
    if denial is not None:
        return StanceSuggestion(
            EvidenceRelation.CONTRADICTS, "strong", [f"calls it false: “{denial.surface}”"]
        )

    kind = item_type
    if kind is None:
        found = classify(text.split("\n", 1)[0], text)
        kind = found.event_type if found else None
    if kind and EVENT_TYPE_FAMILY.get(kind) != event.family:
        return StanceSuggestion(
            EvidenceRelation.UNRELATED,
            "medium",
            [f"about {_a(kind)}, not {_a(event.event_type)}"],
        )

    comparable = [c for c in claims if c.attribute in details.COMPARABLE]
    conflicts, reasons = _disagreements(db, event, comparable, exclude)
    if conflicts:
        return StanceSuggestion(EvidenceRelation.PARTIALLY_SUPPORTS, "medium", reasons, conflicts)

    if not comparable and RELATED_CUES.search(text):
        return StanceSuggestion(
            EvidenceRelation.RELATED, "weak", ["asks or comments; states nothing checkable"]
        )

    reasons = ["reports it; nothing in it says otherwise"]
    if kind and kind == event.event_type:
        reasons = [f"reports {_a(kind)}, like the event; nothing in it says otherwise"]
    return StanceSuggestion(EvidenceRelation.SUPPORTS, "weak", reasons)


def _disagreements(db, event: Event, comparable, exclude) -> tuple[list[str], list[str]]:
    """Details this text states differently from the event's other credible sources."""
    if not comparable:
        return [], []
    from app.services import assess

    skip = assess.copied(db, event) | ({exclude} if exclude else set())
    weights, _ = assess.current_weights(db)
    summaries, _ = assess.summarise_details(assess.votes(event, skip), weights)
    by_attribute = {s.attribute: s for s in summaries}
    conflicts, reasons = [], []
    for c in comparable:
        s = by_attribute.get(c.attribute)
        if s is None or not any(x.reliability >= assess.CREDIBLE for x in s.statements):
            continue
        if not details.agrees(c.attribute, c.value, s.estimate):
            conflicts.append(c.attribute)
            reasons.append(
                f"says {_value(c.attribute, c.value, c.unit)}; other sources say "
                f"{_value(c.attribute, s.estimate, s.unit)}"
            )
    return conflicts, reasons


def for_audit(s: StanceSuggestion, chosen: str) -> dict:
    return {
        "relation": s.relation.value,
        "strength": s.strength,
        "followed": s.relation.value == chosen,
    }


# --- How well suggestions match analysts --------------------------------------------------

LABELS = [r.value for r in EvidenceRelation]


def _scores(pairs: list[tuple[str, str]]) -> dict:
    """Accuracy, per-relation precision / recall / F1 and the confusion counts of
    (suggested, labelled) pairs."""
    n = len(pairs)
    confusion: dict[str, dict[str, int]] = {g: {p: 0 for p in LABELS} for g in LABELS}
    for suggested, labelled in pairs:
        confusion[labelled][suggested] += 1
    per = {}
    for label in LABELS:
        tp = confusion[label][label]
        predicted = sum(confusion[g][label] for g in LABELS)
        actual = sum(confusion[label].values())
        p = tp / predicted if predicted else None
        r = tp / actual if actual else None
        # 2·TP / (predicted + labelled): 0 when a label is never suggested (or never right).
        f = 2 * tp / (predicted + actual) if predicted + actual else None
        per[label] = {"labelled": actual, "precision": p, "recall": r, "f1": f}
    scored = [v["f1"] for v in per.values() if v["labelled"]]
    return {
        "n": n,
        "accuracy": sum(confusion[x][x] for x in LABELS) / n if n else None,
        "macro_f1": sum(scored) / len(scored) if scored else None,
        "per_relation": per,
        "confusion": confusion,  # labelled -> suggested -> count
    }


def evaluate(db) -> dict:
    """Suggestions for every link (each read without itself) against (a) annotators'
    blind second opinions, made without seeing any suggestion: the fair test; and (b)
    the working or adjudicated label, which may have been set with the suggestion in
    view. Also: how often analysts followed a suggestion, from the audit log."""
    from sqlalchemy import select

    from app.models.audit import AuditLog
    from app.models.event import EventEvidence
    from app.services import audit
    from app.services.details import headline_and_text

    blind, working = [], []
    for link in db.scalars(select(EventEvidence)).all():
        source = link.field_report or link.signal
        text = (
            link.field_report.text
            if link.field_report
            else headline_and_text(link.signal.title, link.signal.text)
        )
        s = suggest(db, link.event, text, item_type=source.event_type, exclude=link.id)
        working.append((s.relation.value, (link.gold_relation or link.relation).value))
        for j in link.judgements:
            if j.blind:
                blind.append((s.relation.value, j.relation.value))
    shown = [
        d["stance_suggested"]
        for d in db.scalars(
            select(AuditLog.details).where(
                AuditLog.action.in_(
                    [audit.AuditAction.EVIDENCE_LINKED, audit.AuditAction.EVIDENCE_UPDATED]
                ),
                AuditLog.details["stance_suggested"].is_not(None),
            )
        ).all()
    ]
    return {
        "blind_second_opinions": _scores(blind),
        "working_labels": _scores(working),
        "followed": {"shown": len(shown), "followed": sum(bool(x["followed"]) for x in shown)},
    }


def _num(x: float | None) -> str:
    return "-" if x is None else f"{x:.3f}"


def _suggested(r: dict, label: str) -> int:
    return sum(row[label] for row in r["confusion"].values())


def table(result: dict) -> str:
    lines = []
    for name, title in (
        ("blind_second_opinions", "Against blind second opinions (made without suggestions)"),
        ("working_labels", "Against working labels (may have seen the suggestion)"),
    ):
        r = result[name]
        lines.append(title)
        if not r["n"]:
            lines += ["  none yet", ""]
            continue
        lines.append(
            f"  {r['n']} labels, accuracy {_num(r['accuracy'])}, macro-F1 {_num(r['macro_f1'])}"
        )
        for label, v in r["per_relation"].items():
            if v["labelled"] or (v["precision"] is not None):
                lines.append(
                    f"  {label:<20} labelled {v['labelled']:>4}   suggested "
                    f"{_suggested(r, label):>4}   F1 {_num(v['f1'])}"
                )
        lines.append("")
    f = result["followed"]
    lines.append(
        f"Links and relation changes with a suggestion shown: {f['shown']}, "
        f"followed {f['followed']}"
    )
    return "\n".join(lines)
