"""When a text says something happened, in Bangla, Banglish and English, made absolute
against the time the text was published (the dataset's `observed_at`).

    times("Gotokal raat 10 tay agun lage", published)   # yesterday, 22:00
    times("আজ সকালে মিরপুরে হাঁটুসমান পানি", published)    # today, 06:00–12:00
    times("The fire broke out at 9:50pm on 29 February", published)

Precision first, as for details: only clear expressions are taken. "kal" / "কাল" alone
means yesterday or tomorrow, so it is left out; "gotokal" / "গতকাল" is taken. Words for
a part of the day give a window; a clock time gives the hour; a date gives the day.
Every result carries the words it came from (`surface`) and is in Bangladesh time.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from carcux_extraction.numbers import BN_DIGITS

DHAKA = timezone(timedelta(hours=6))


@dataclass(frozen=True)
class TimeMention:
    surface: str
    start: datetime  # the earliest moment meant
    end: datetime  # the latest (start == end for an exact clock time)
    precision: str  # "minute", "part_of_day" or "day"


# --- Words ------------------------------------------------------------------------------

# Days before the publication day.
DAY_WORDS = [
    (r"day before yesterday|গত পরশু|gotoporshu|goto porshu", 2),
    (r"yesterday|last night|গতকাল|গতকালকে|গত রাতে|গতরাতে|গত রাত|gotokal|gotokaal|gotokalke"
     r"|goto raat|goto rat|gotorat|gotoraat", 1),
    (r"today|tonight|this morning|this afternoon|this evening|আজ|আজকে|ajke|ajk|aj|aaj", 0),
]  # fmt: skip

# Parts of the day: (words, first hour, last hour, the hour a bare clock time starts at).
PARTS = [
    ("dawn", r"dawn|daybreak|ভোর|ভোরে|bhor|bhore|vor|vore", 4, 6, 0),
    ("morning", r"morning|সকাল|সকালে|sokal|sokale|shokal|shokale", 6, 12, 0),
    ("noon", r"noon|midday|দুপুর|দুপুরে|dupur|dupure", 12, 15, 12),
    ("afternoon", r"afternoon|বিকাল|বিকালে|বিকেল|বিকেলে|bikal|bikale|bikel|bikele", 15, 18, 12),
    ("evening", r"evening|সন্ধ্যা|সন্ধ্যায়|sondha|sondhay|sondhya|sondhyay|shondha", 18, 20, 12),
    ("night", r"night|tonight|রাত|রাতে|raat|raate|rat|rate|ratri", 20, 24, 12),
]
_PART_OF = {}
for _name, words, *_ in PARTS:
    for w in words.split("|"):
        _PART_OF[w] = _name
PART = {p[0]: p for p in PARTS}

MONTHS = {
    **dict.fromkeys(["january", "jan", "জানুয়ারি", "জানুয়ারী"], 1),
    **dict.fromkeys(["february", "feb", "ফেব্রুয়ারি", "ফেব্রুয়ারী"], 2),
    **dict.fromkeys(["march", "mar", "মার্চ"], 3),
    **dict.fromkeys(["april", "apr", "এপ্রিল"], 4),
    **dict.fromkeys(["may", "মে"], 5),
    **dict.fromkeys(["june", "jun", "জুন"], 6),
    **dict.fromkeys(["july", "jul", "জুলাই"], 7),
    **dict.fromkeys(["august", "aug", "আগস্ট", "অগাস্ট"], 8),
    **dict.fromkeys(["september", "sep", "sept", "সেপ্টেম্বর"], 9),
    **dict.fromkeys(["october", "oct", "অক্টোবর"], 10),
    **dict.fromkeys(["november", "nov", "নভেম্বর"], 11),
    **dict.fromkeys(["december", "dec", "ডিসেম্বর"], 12),
}

_B = r"(?<![\wঀ-৿])"  # word start (Latin or Bangla)
_E = r"(?![\wঀ-৿])"  # word end
_DAY = "|".join(f"(?:{w})" for w, _ in DAY_WORDS)
_PARTW = "|".join(sorted(_PART_OF, key=len, reverse=True))
_MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))
_NUM = r"[0-9০-৯]{1,2}"
# A clock time: 9:50pm, 10.30 am, 10 am, ১০টায়, 10 tay, 9 tar dike.
_CLOCK = (
    rf"(?P<h>{_NUM})(?:[:.](?P<m>[0-9০-৯]{{2}}))?\s*"
    r"(?:(?P<ampm>a\.?m\.?|p\.?m\.?)|(?:টার দিকে|টায়|টার|টা|tar dike|ta dike|tay|tai|tar|ta"
    r"|o'?clock))"
    rf"(?:\s*(?P<m2>{_NUM})\s*(?:মিনিটে|মিনিট|minutes?|min))?"
)
_DATE = (
    rf"(?:(?P<d1>{_NUM})(?:st|nd|rd|th)?\s+(?P<mon1>{_MONTH})|(?P<mon2>{_MONTH})\s+(?P<d2>{_NUM})"
    rf"(?:st|nd|rd|th)?)(?:,?\s+(?P<y>(?:19|20|১৯|২০)[0-9০-৯]{{2}}))?"
)

PATTERN = re.compile(
    rf"{_B}(?:(?P<day>{_DAY})\s*(?:(?:at\s+)?(?P<part1>{_PARTW}))?{_E}"
    rf"|(?P<date>{_DATE}){_E}"
    rf"|(?:(?P<part2>{_PARTW})\s+)?(?:at\s+)?(?P<clock>{_CLOCK}){_E})",
    re.IGNORECASE,
)
# A clock time right after a day or a date: "yesterday at 10pm", "29 February at 9:50pm".
TAIL = re.compile(rf"\s*(?:,|at|এ|on)?\s*(?:(?P<part>{_PARTW})\s+)?(?P<clock>{_CLOCK}){_E}", re.I)


def _int(s: str) -> int:
    return int(s.translate(BN_DIGITS))


def _hour(h: int, minute: int, ampm: str | None, part: str | None) -> tuple[int, int] | None:
    if ampm:
        pm = ampm.lower().startswith("p")
        if not 1 <= h <= 12:
            return None
        h = (h % 12) + (12 if pm else 0)
    elif part:
        # "raat 10 tay" is 22:00, "sokal 9 tay" 09:00, "rat 1 tay" 01:00.
        if part == "night" and h <= 4:
            pass
        elif h < 12:
            h += PART[part][4]
    if not (0 <= h <= 23 and 0 <= minute <= 59):
        return None
    return h, minute


def _day_offset(words: str) -> int:
    for pattern, offset in DAY_WORDS:
        if re.fullmatch(pattern, words.strip(), re.IGNORECASE):
            return offset
    return 0


def _date(m: re.Match, ref: datetime) -> date | None:
    day_n = _int(m.group("d1") or m.group("d2"))
    month = MONTHS[(m.group("mon1") or m.group("mon2")).lower()]
    year = _int(m.group("y")) if m.group("y") else ref.year
    try:
        day = date(year, month, day_n)
    except ValueError:
        return None
    if not m.group("y") and day > ref.date() + timedelta(days=1):
        day = date(year - 1, month, day_n)  # "21 November" said in January
    return day


def times(text: str, published: datetime) -> list[TimeMention]:
    """Every clear time expression in the text, made absolute in Bangladesh time."""
    ref = published.astimezone(DHAKA)
    text = text or ""
    out: list[TimeMention] = []
    pos = 0
    while (m := PATTERN.search(text, pos)) is not None:
        pos = m.end()
        day: date | None = None
        part = None
        surface_end = m.end()
        if m.group("day"):
            words = m.group("day")
            day = ref.date() - timedelta(days=_day_offset(words))
            low = words.lower()
            part = _PART_OF.get((m.group("part1") or "").lower())
            if part is None and ("night" in low or "রাত" in words or "rat" in low):
                part = "night"
            elif part is None and "morning" in low:
                part = "morning"
            elif part is None and "afternoon" in low:
                part = "afternoon"
            elif part is None and "evening" in low:
                part = "evening"
        elif m.group("date"):
            day = _date(m, ref)
            if day is None:
                continue
        clock = None
        dated = False
        if m.group("clock"):
            part = _PART_OF.get((m.group("part2") or "").lower())
            clock = m
            day = ref.date()
            # "at 9:50pm on 29 February": the date that follows gives the day.
            on = re.compile(rf"\s*(?:,|on)?\s*(?P<date>{_DATE}){_E}", re.I).match(text, m.end())
            if on:
                found = _date(on, ref)
                if found:
                    day, dated, surface_end = found, True, on.end()
        elif day is not None:
            tail = TAIL.match(text, m.end())
            if tail:
                part = _PART_OF.get((tail.group("part") or "").lower()) or part
                clock, surface_end = tail, tail.end()
        if clock is not None:
            minute = clock.group("m") or clock.group("m2") or "0"
            hm = _hour(_int(clock.group("h")), _int(minute), clock.group("ampm"), part)
            if hm is None:
                continue
            at = datetime.combine(day, time(*hm), DHAKA)
            undated = not (m.group("day") or m.group("date") or dated)
            if undated and at > ref + timedelta(minutes=30):
                at -= timedelta(days=1)  # "at 10pm", said the next morning
            out.append(TimeMention(text[m.start() : surface_end], at, at, "minute"))
            pos = max(pos, surface_end)
            continue
        if day is None:
            continue
        if part:
            _, _, first, last, _ = PART[part]
            start = datetime.combine(day, time(first), DHAKA)
            end = datetime.combine(day, time(0), DHAKA) + timedelta(hours=last)
            if part == "night" and m.group("day") and _day_offset(m.group("day")) == 1:
                end += timedelta(hours=6)  # last night runs into the small hours
            out.append(TimeMention(text[m.start() : surface_end], start, end, "part_of_day"))
        else:
            start = datetime.combine(day, time(0), DHAKA)
            out.append(TimeMention(text[m.start() : surface_end], start,
                                   start + timedelta(days=1), "day"))  # fmt: skip
    return out


def observed_at(text: str, published: datetime) -> datetime | None:
    """When the text says the situation was seen: its earliest clear time that is not
    after publication (an item cannot report the future)."""
    ref = published.astimezone(DHAKA)
    seen = [t.start for t in times(text, published) if t.start <= ref]
    return min(seen) if seen else None
