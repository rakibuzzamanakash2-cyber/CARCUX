"""Numbers as people write them in reports: 1,250 · ১২৫০ · 1.5 lakh · দেড় লাখ · tin hajar ·
two dozen · কয়েকশ (vague: no number).

`NUMBER` is a regular expression for one number phrase; `value(text)` turns a matched
phrase into a number, or None when it is vague ("hundreds of", "koyekjon").
"""

import re
import unicodedata

BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

# Small numbers as words. Bangla script, Banglish, English.
UNITS: dict[str, float] = {
    # Bangla
    "এক": 1, "একজন": 1, "দুই": 2, "দু": 2, "তিন": 3, "চার": 4, "পাঁচ": 5, "ছয়": 6,
    "সাত": 7, "আট": 8, "নয়": 9, "দশ": 10, "এগারো": 11, "বারো": 12, "তেরো": 13,
    "চৌদ্দ": 14, "পনেরো": 15, "ষোলো": 16, "সতেরো": 17, "আঠারো": 18, "উনিশ": 19, "বিশ": 20,
    "পঁচিশ": 25, "ত্রিশ": 30, "চল্লিশ": 40, "পঞ্চাশ": 50, "ষাট": 60, "সত্তর": 70, "আশি": 80,
    "নব্বই": 90, "দেড়": 1.5, "আড়াই": 2.5,
    # Banglish
    "ek": 1, "dui": 2, "du": 2, "tin": 3, "teen": 3, "char": 4, "panch": 5, "pach": 5,
    "choy": 6, "chhoy": 6, "sat": 7, "shat": 7, "at": 8, "aat": 8, "noy": 9, "dosh": 10,
    "das": 10, "bish": 20, "tirish": 30, "chollish": 40, "ponchash": 50, "der": 1.5,
    "deer": 1.5, "arai": 2.5,
    # English
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}  # fmt: skip
SCALES: dict[str, float] = {
    "শ": 100, "শো": 100, "শত": 100, "হাজার": 1_000, "লাখ": 100_000, "লক্ষ": 100_000,
    "কোটি": 10_000_000,
    "sho": 100, "shoto": 100, "hajar": 1_000, "hazar": 1_000, "lakh": 100_000,
    "lac": 100_000, "lacs": 100_000, "lakhs": 100_000, "koti": 10_000_000,
    "crore": 10_000_000, "crores": 10_000_000,
    "hundred": 100, "hundreds": 100, "thousand": 1_000, "thousands": 1_000,
    "million": 1_000_000, "dozen": 12, "dozens": 12,
}  # fmt: skip
# Plural scales without a number in front ("hundreds of", "kayek hajar") are vague.
VAGUE = re.compile(
    r"^(?:hundreds|thousands|dozens|lakhs|crores|several|many|some|koyek|kayek|koek|"
    r"bohu|onek|কয়েক|কয়েক|বহু|অনেক|শত শত|হাজার হাজার)",
    re.IGNORECASE,
)

_DIGIT = r"[0-9০-৯]+(?:[,.][0-9০-৯]+)*"
_UNIT_WORDS = "|".join(sorted(map(re.escape, UNITS), key=len, reverse=True))
_SCALE_WORDS = "|".join(sorted(map(re.escape, SCALES), key=len, reverse=True))
WORD_CHAR = r"\wঀ-৿"  # \w misses Bangla vowel signs
# A number: digits or a number word, optionally followed by a scale word ("1.5 lakh",
# "তিন হাজার"). No word boundary after it: Bangla writes "তিনজন" as one word.
NUMBER = (
    rf"(?:(?<![{WORD_CHAR}.,])(?:{_DIGIT}|{_UNIT_WORDS})"
    rf"(?:\s*(?:{_SCALE_WORDS})(?![a-z]))?)"
)
_SPLIT = re.compile(rf"^({_DIGIT}|{_UNIT_WORDS})?\s*({_SCALE_WORDS})?$", re.IGNORECASE)


def _digits(s: str) -> float | None:
    s = s.translate(BN_DIGITS)
    # 1,250 and 12,50,000 (Indian grouping) are thousands separators; 1.5 is a decimal.
    if "," in s and "." not in s:
        s = s.replace(",", "")
    elif s.count(".") == 1 and "," not in s:
        pass
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def normalise(text: str) -> str:
    """One Unicode form for Bangla: য়, ড়, ঢ় can be stored precomposed or as letter plus
    nukta; NFC gives the latter, which is how the word lists here are written."""
    return unicodedata.normalize("NFC", text)


def value(text: str) -> float | None:
    """The number a phrase states, or None if it states none or only a vague amount."""
    text = normalise(text).strip()
    if not text or VAGUE.match(text):
        return None
    m = _SPLIT.match(text)
    if not m:
        return None
    head, scale = m.group(1), m.group(2)
    if head is None:
        return None  # a bare scale word: "hundreds", "hajar" on its own is vague
    n = _digits(head) if re.match(r"[0-9০-৯]", head) else UNITS.get(head.lower(), UNITS.get(head))
    if n is None:
        return None
    if scale:
        n *= SCALES.get(scale.lower(), SCALES.get(scale, 1))
    return n


def as_int(n: float | None) -> int | None:
    return None if n is None else round(n)
