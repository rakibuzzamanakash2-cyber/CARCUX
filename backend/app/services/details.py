"""Details stated in a report's or a signal's text (deaths, people affected, depth,
cause, status, denials), from the extraction module (app/extraction).

Worked out when needed, not stored: report text never changes, extraction takes
milliseconds, and improved rules then apply to everything already collected.
"""

from app.extraction import Claim, extract
from app.models.field_report import FieldReport
from app.models.signal import Signal

# Details that can disagree between reports about the same event. Status changes over
# time and occurrence is the stance, so neither is a disputed detail.
COMPARABLE = ("magnitude", "affected_count", "casualty_count", "cause")
COUNT_TOLERANCE = 0.20  # annotation guideline §5.2: counts agree within ±20 %


def headline_and_text(title: str, text: str | None) -> str:
    """A signal's words: its headline, then its text unless the text repeats it."""
    title, text = title.strip(), (text or "").strip()
    if not text or text.startswith(title):
        return text or title
    return f"{title}. {text}"


def signal_text(s: Signal) -> str:
    return headline_and_text(s.title, s.text)


def for_report(r: FieldReport) -> list[Claim]:
    return extract(r.text)


def for_signal(s: Signal) -> list[Claim]:
    return extract(signal_text(s))


def agrees(attribute: str, a, b) -> bool:
    """Whether two stated values agree, as the annotation guideline compares them."""
    if attribute in ("affected_count", "casualty_count"):
        a, b = float(a), float(b)
        top = max(abs(a), abs(b))
        return a == b if top == 0 else abs(a - b) <= COUNT_TOLERANCE * top
    if attribute == "cause" and "unknown" in (a, b):
        return True  # "cause unknown" does not contradict a stated cause
    return a == b
