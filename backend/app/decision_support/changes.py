"""What changed since a moment: new evidence, new denials, counts that moved, and the
analysts' decisions (from the audit log, passed in by the backend). Evidence-based
sentences cite their items; decisions say who decided nothing about, only what."""

from dataclasses import dataclass
from datetime import datetime

from app.decision_support.model import COUNTS, SUPPORTING, EventFacts, label
from app.decision_support.summary import Sentence, _ids, _n, when


@dataclass(frozen=True)
class LogEntry:
    at: datetime
    text: str  # e.g. "Status set to monitoring."


def what_changed(
    event: EventFacts, since: datetime, now: datetime, log: list[LogEntry] = ()
) -> list[Sentence]:
    counted = event.counted()
    new = sorted((e for e in counted if since < e.at <= now), key=lambda e: e.at)
    out: list[Sentence] = []
    if new:
        sup = [e for e in new if e.relation in SUPPORTING]
        den = [e for e in new if e.relation == "contradicts"]
        rel = [e for e in new if e.relation == "related"]
        parts = [f"{len(sup)} support it"] if sup else []
        parts += [f"{len(den)} say it did not happen"] if den else []
        parts += [f"{len(rel)} only comment"] if rel else []
        n = len(new)
        out.append(Sentence(f"{n} new {'item' if n == 1 else 'items'}: {', '.join(parts)}.",
                            _ids(new), "new"))  # fmt: skip
        for e in den:
            words = f": “{e.denial}”" if e.denial else ""
            out.append(Sentence(f"New denial from {e.source}{words}.", [e.id], "denial"))

    for attribute in sorted(COUNTS):
        moved = _moved(event, attribute, since, now)
        if moved:
            out.append(moved)

    for entry in sorted(log, key=lambda x: x.at):
        if since < entry.at <= now:
            out.append(Sentence(f"{when(entry.at)}: {entry.text}", [], "decision"))

    if not out:
        out.append(Sentence(f"Nothing new since {when(since)}.", [], "none"))
    return out


def _moved(event: EventFacts, attribute: str, since: datetime, now: datetime):
    said = sorted(
        (
            (e.at, float(d.value), e)
            for e in event.counted()
            if e.relation in SUPPORTING
            for d in e.details
            if d.attribute == attribute and isinstance(d.value, int | float)
        ),
        key=lambda x: (x[0], x[1], x[2].id),  # items themselves are not ordered
    )
    before = [x for x in said if x[0] <= since]
    after = [x for x in said if since < x[0] <= now]
    if not after:
        return None
    top_after = max(after, key=lambda x: x[1])
    if before:
        top_before = max(before, key=lambda x: x[1])
        if top_after[1] <= top_before[1] * 1.2:
            return None
        return Sentence(
            f"{label(attribute)}: {top_after[2].source} now says {_n(top_after[1])}, "
            f"up from {_n(top_before[1])}.",
            [top_after[2].id, top_before[2].id], "count",
        )  # fmt: skip
    return Sentence(f"{label(attribute)}: first figure, {_n(top_after[1])} "
                    f"({top_after[2].source}).", [top_after[2].id], "count")  # fmt: skip
