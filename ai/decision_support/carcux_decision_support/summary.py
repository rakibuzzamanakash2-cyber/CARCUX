"""Evidence-referenced summaries: every sentence cites the items it rests on.

A sentence that cannot point to evidence is not written; when there is no evidence at
all, the summary says so instead of guessing. Sources are named as the evidence names
them (outlets and pages by name, field workers as "A field worker").
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from carcux_decision_support.model import (
    COUNTS,
    CREDIBLE,
    FIELD_WORKER,
    SUPPORTING,
    Estimate,
    EventFacts,
    Evidence,
    label,
    type_label,
)

DHAKA = ZoneInfo("Asia/Dhaka")
COUNT_TOLERANCE = 0.20  # guideline §5.2
COUNT_WINDOW = timedelta(hours=12)  # guideline v0.4: counts said this close are compared


@dataclass
class Sentence:
    text: str
    cites: list[str] = field(default_factory=list)  # evidence ids
    kind: str = ""


def when(dt: datetime, tz=DHAKA) -> str:
    return dt.astimezone(tz).strftime("%d %b %Y, %H:%M")


def _value(attribute: str, value, unit: str | None) -> str:
    if attribute == "casualty_count":
        return f"{_n(value)} dead"
    if attribute == "affected_count":
        return f"{_n(value)} {unit or 'people'}"
    return str(value)


def _n(value) -> str:
    v = float(value)
    return f"{int(v):,}" if v.is_integer() else f"{v:,.1f}"


def _agrees(attribute: str, a, b) -> bool:
    if attribute in COUNTS:
        a, b = float(a), float(b)
        top = max(abs(a), abs(b))
        return a == b if top == 0 else abs(a - b) <= COUNT_TOLERANCE * top
    return a == b or "unknown" in (a, b)


def _names(items: list[Evidence]) -> str:
    # One name per source; several field workers become "2 field workers".
    by_name: dict[str, set[str]] = {}
    for e in items:
        by_name.setdefault(e.source, set()).add(e.key)
    names = [
        f"{len(keys)} field workers" if name == FIELD_WORKER and len(keys) > 1 else name
        for name, keys in by_name.items()
    ]
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{names[0]} and {len(names) - 1} others"


def _ids(items) -> list[str]:
    return list(dict.fromkeys(e.id for e in items))


def summarise(event: EventFacts, now: datetime | None = None) -> list[Sentence]:
    counted = event.counted()
    supporting = sorted((e for e in counted if e.relation in SUPPORTING), key=lambda e: e.at)
    denying = sorted((e for e in counted if e.relation == "contradicts"), key=lambda e: e.at)
    out: list[Sentence] = []

    where = f" at {event.place_name}" if event.place_name else ""
    since = f"since {when(event.started_at)}"
    if event.ended_at:
        since = f"from {when(event.started_at)} to {when(event.ended_at)}"
    lead = f"{type_label(event.event_type).capitalize()}{where}, {since}."
    if not supporting and not denying:
        return [Sentence(lead + " No evidence is linked yet, so there is nothing to summarise.",
                         [], "lead")]  # fmt: skip
    out.append(Sentence(lead, _ids(supporting[:3] or denying[:1]), "lead"))

    credible = [e for e in supporting if (e.reliability or 0) >= CREDIBLE]
    parts = [f"{len({e.key for e in supporting})} sources say it happened"]
    if supporting:
        parts[0] += f" ({len({e.key for e in credible})} credible)"
    if denying:
        n = len({e.key for e in denying})
        parts.append(f"{n} {'says' if n == 1 else 'say'} it did not")
    out.append(Sentence("; ".join(parts) + ".", _ids(supporting + denying), "balance"))

    for e in denying[:3]:
        words = f": “{e.denial}”" if e.denial else ""
        out.append(Sentence(f"{e.source} calls it false{words}.", [e.id], "denial"))

    for est in event.estimates:
        s = _detail(est, supporting)
        if s:
            out.append(s)

    wrong: dict[str, list[Evidence]] = {}
    for e in supporting:
        for c in e.conflicts:
            wrong.setdefault(c, []).append(e)
    if wrong:
        listed = ", ".join(f"{label(a).lower()} ({len(v)})" for a, v in wrong.items())
        items = [e for v in wrong.values() for e in v]
        out.append(Sentence(f"Analysts found details wrong in some items: {listed}.",
                            _ids(items), "conflicts"))  # fmt: skip

    copies = [e for e in event.evidence if e.copy_of is not None]
    if copies:
        n = len(copies)
        out.append(Sentence(
            f"{n} {'item repeats' if n == 1 else 'items repeat'} an earlier one and "
            f"{'is' if n == 1 else 'are'} counted once.",
            _ids(copies), "copies",
        ))  # fmt: skip

    latest = max(counted, key=lambda e: e.at, default=None)
    if latest is not None:
        what = f": “{latest.headline}”" if latest.headline else ""
        out.append(Sentence(f"Latest: {latest.source}, {when(latest.at)}{what}.",
                            [latest.id], "latest"))  # fmt: skip
    return out


def _stating(attribute: str, items: list[Evidence]) -> list[tuple[Evidence, object]]:
    return [(e, d.value) for e in items for d in e.details if d.attribute == attribute]


def _detail(est: Estimate, supporting: list[Evidence]) -> Sentence | None:
    stated = _stating(est.attribute, supporting)
    if not stated:
        return None
    name = label(est.attribute)
    if est.disputed:
        pair = _disputing_pair(est.attribute, stated)
        if pair:
            (a, va), (b, vb) = pair
            return Sentence(
                f"{name} is disputed: {a.source} says {_value(est.attribute, va, est.unit)}; "
                f"{b.source} says {_value(est.attribute, vb, est.unit)}.",
                [a.id, b.id], "disputed",
            )  # fmt: skip
    agreeing = [e for e, v in stated if _agrees(est.attribute, v, est.value)]
    if not agreeing:
        return None
    verb = "says" if len({e.key for e in agreeing}) == 1 else "say"
    text = f"{name}: {_value(est.attribute, est.value, est.unit)}, as {_names(agreeing)} {verb}."
    cites = _ids(agreeing)
    if est.attribute in COUNTS:
        first = min(e.at for e in agreeing)
        earlier = [(e, v) for e, v in stated if e.at < first and float(v) < float(est.value)]
        if earlier:
            in_order = sorted(earlier, key=lambda x: x[0].at)
            values = ", ".join(dict.fromkeys(_n(v) for _, v in in_order))
            text += f" Earlier reports gave {values} as the figure rose."
            cites += _ids(e for e, _ in earlier)
    return Sentence(text, list(dict.fromkeys(cites)), "detail")


def _disputing_pair(attribute: str, stated):
    """Two credible items that disagree, said close enough in time to compare."""
    ranked = sorted(stated, key=lambda x: -(x[0].reliability or 0))
    for i, (a, va) in enumerate(ranked):
        for b, vb in ranked[i + 1 :]:
            if a.key == b.key or _agrees(attribute, va, vb):
                continue
            if attribute in COUNTS and abs(a.at - b.at) > COUNT_WINDOW:
                continue
            return (a, va), (b, vb)
    return None
