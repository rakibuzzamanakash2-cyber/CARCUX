"""Checkable details in a report, as CARCUX-BD claims (annotation guideline §4.2).

    extract("Mirpur 10 e hatu pani, 3 jon mara geche bhari brishtir karone")
    -> magnitude knee-deep, casualty_count 3, cause heavy rain

Transparent rules in Bangla, Banglish and English, so every claim says which words it
came from (`surface`). Precision first: a detail is only taken when the wording is
clear; vague amounts ("hundreds", "koyekjon") give no number. What is extracted:

- **occurrence = false** when the item denies the event or calls it a rumour (nothing
  is said otherwise: an item about an event claims it by default);
- **casualty_count**: deaths ("3 killed", "তিনজন নিহত", "3 jon mara geche"); "no
  casualties" gives 0. Injuries are not counted here (the guideline's casualty count
  is deaths);
- **affected_count**: people or households affected, stranded, marooned, displaced,
  evacuated, homeless, in shelters (unit "people" or "households");
- **magnitude**: water depth on the guideline's scale (ankle-deep, knee-deep,
  waist-deep, chest-deep, above-head, from "hatu pani", "হাঁটুসমান পানি", "knee-deep"),
  and fire size (large, small) from clear wording ("massive fire", "ভয়াবহ আগুন");
- **cause**: a short normalised phrase (heavy rain, river overflow, embankment breach,
  upstream runoff, blocked drains, electrical short circuit, gas leak, cylinder
  explosion, vehicle collision, protest, maintenance work, unknown). Causes that could
  also be the event itself (rain, a river rising, a protest) need a causal cue: "due
  to", "after", "কারণে", "বৃষ্টিতে", "karone", "cause:";
- **status**: resolved, worsening, improving or ongoing, from clear wording ("water has
  receded", "পানি বাড়ছে", "ekhono").

One claim per attribute; for counts, the largest stated (death tolls are updated
upwards).
"""

import re
from dataclasses import dataclass

from app.extraction.numbers import NUMBER, WORD_CHAR, as_int, normalise, value

IC = re.IGNORECASE
SURFACE_MAX = 200
NOT_BEFORE = rf"(?<![{WORD_CHAR}])"  # start of a word, Bangla included


@dataclass(frozen=True)
class Claim:
    attribute: str
    value: object
    unit: str | None = None
    surface: str = ""

    def as_dict(self) -> dict:
        out: dict = {"attribute": self.attribute, "value": self.value}
        if self.unit:
            out["unit"] = self.unit
        if self.surface:
            out["surface"] = self.surface[:SURFACE_MAX]
        return out


def _c(pattern: str) -> re.Pattern:
    return re.compile(normalise(pattern), IC)


N = rf"(?P<n>{NUMBER})"
# Up to three (two) words between a number and what it counts, never across a clause
# end: "একজন নিহত, তিনজন আহত" is one death, not three.
GAP = r"(?:[^\s.,;।!?]+\s+){0,3}?"
BN_GAP = r"(?:[^\s.,;।!?]+\s+){0,2}?"
ABOUT = r"(?:(?:at least|about|around|nearly|almost|over|more than|some|approximately|প্রায়|প্রায়|অন্তত|কমপক্ষে|prai|praay|ontoto|komopokkhe)\s+)?"

# --- Deaths -------------------------------------------------------------------------------

DEATHS = [
    # English
    _c(
        rf"{N}\s+(?:people\s+|persons\s+|of them\s+|workers\s+|children\s+)?(?:were\s+|have been\s+|are\s+|had been\s+)?(?:killed|dead|died|drowned|deaths?\b|bodies|lost their lives)"
    ),
    _c(rf"(?:killing|killed|claimed the lives of|claiming the lives of)\s+{ABOUT}{N}"),
    _c(rf"death toll\s+(?:[^\s.;।!?]+\s+){{0,8}}?(?:to|at|of|reached|is|hits?)?\s*{N}"),
    # Bangla
    _c(rf"{N}\s*জন(?:ের|ে)?\s*{BN_GAP}(?:নিহত|মৃত|মারা|প্রাণ হারি|প্রাণহানি|লাশ)"),
    _c(rf"(?:নিহত|মৃতের সংখ্যা|মৃত্যু হয়েছে|প্রাণ গেছে)\s+{BN_GAP}{N}\s*জন"),
    # Banglish
    _c(
        rf"{N}\s*(?:jon|joner|jn|ta lash|jon er)\s+{GAP}(?:nihoto|nihito|nihot|mara|mrito|mrittu|lash|prothom moron)"
    ),
    _c(rf"(?:nihoto|mara gese|mara geche|mara gelo)\s+{ABOUT}{N}\s*(?:jon|jn)"),
]
NO_DEATHS = [
    _c(
        r"no (?:casualt(?:y|ies)|deaths?|loss of life|one (?:was |has been )?(?:killed|hurt|died))|nobody (?:was |has been )?(?:killed|hurt|died)|no one died|no fatalit(?:y|ies)"
    ),
    _c(
        r"কেউ\s*(?:নিহত|হতাহত|মারা)\s*(?:হয়নি|হয়নি|যায়নি|যায়নি|যাননি|হননি)|কোনো\s*(?:হতাহতের|প্রাণহানির)\s*(?:খবর|ঘটনা)?\s*(?:পাওয়া যায়নি|পাওয়া যায়নি|নেই|ঘটেনি)"
    ),
    _c(
        r"keu\s+(?:mara|nihoto|hotahot)\s+(?:jay ?nai|jai ?nai|jayni|jaini|hoy ?nai|hoyni)|kono\s+hotahot\s+(?:hoy ?nai|hoyni|nai|nei)"
    ),
]

# --- People affected ------------------------------------------------------------------------

HOUSEHOLDS = (
    r"(?:families|family|households|homes|houses|পরিবার|পরিবারের|ঘরবাড়ি|বাড়িঘর|poribar|paribar|family)"
)
EN_AFFECTED = r"(?:affected|stranded|marooned|displaced|evacuated|homeless|trapped|waterlogged|submerged|inundated|without (?:power|electricity|food|water)|in (?:the )?shelters?|(?:moved|taken|shifted) to (?:the )?shelters?|took shelter)"
AFFECTED = [
    _c(
        rf"{N}\s+(?P<u>people|persons|residents|villagers|inhabitants|{HOUSEHOLDS})\s+{GAP}{EN_AFFECTED}"
    ),
    _c(
        rf"(?:affecting|affected|stranding|stranded|marooned|displacing|displaced|evacuated|leaving)\s+{ABOUT}{N}\s+(?P<u>people|persons|residents|villagers|{HOUSEHOLDS})"
    ),
    _c(
        rf"{N}\s*(?:টি\s*)?(?P<u>জন|মানুষ|লোক|বাসিন্দা|{HOUSEHOLDS})\s*{BN_GAP}(?:ক্ষতিগ্রস্ত|পানিবন্দী|পানিবন্দি|আটকা|আটকে|গৃহহীন|আশ্রয়|আশ্রয়|বাস্তুচ্যুত|বিদ্যুৎহীন)"
    ),
    _c(
        rf"(?:পানিবন্দী|পানিবন্দি|ক্ষতিগ্রস্ত|গৃহহীন)\s*(?:হয়ে পড়েছে|হয়ে পড়েছে|হয়েছে|হয়েছে|রয়েছে|রয়েছে)?\s*{ABOUT}{N}\s*(?P<u>জন|মানুষ|লোক|{HOUSEHOLDS})"
    ),
    _c(
        rf"{N}\s*(?P<u>jon|manush|lok|{HOUSEHOLDS})\s+{GAP}(?:khotigrosto|khotigrsto|pani\s*bondi|panibondi|atka|atke|grihohin|ashroy|bastuchuto)"
    ),
]

# --- Magnitude ---------------------------------------------------------------------------

WATER = r"(?:পানি|জল|pani|paani|water)"
DEPTH: list[tuple[str, re.Pattern]] = [
    (
        "above-head",
        _c(
            r"(?:above|over)\s+(?:the\s+|a person's\s+|people's\s+)?heads?|roof[- ]?(?:deep|high|level)|up to (?:the )?roofs?|মাথার\s*(?:ওপর|উপর)|মাথা\s*সমান|ছাদ\s*(?:পর্যন্ত|সমান)|mathar\s+(?:upor|opor)|matha\s+(?:shoman|soman)"
        ),
    ),
    (
        "chest-deep",
        _c(
            rf"chest[- ]?(?:deep|high|level)|up to (?:the |their )?chests?|{NOT_BEFORE}বুক\s*(?:সমান|পর্যন্ত)?\s*{WATER}|\bbuk\s*(?:shoman|soman|porjonto|obdi)?\s*{WATER}"
        ),
    ),
    (
        "waist-deep",
        _c(
            rf"waist[- ]?(?:deep|high|level)|up to (?:the |their )?waists?|{NOT_BEFORE}কোমর\s*(?:সমান|পর্যন্ত)?\s*{WATER}|\bkomor\s*(?:shoman|soman|porjonto|obdi)?\s*{WATER}"
        ),
    ),
    (
        "knee-deep",
        _c(
            rf"knee[- ]?(?:deep|high|level)|up to (?:the |their )?knees?|{NOT_BEFORE}(?:হাঁটু|হাটু)\s*(?:সমান|পর্যন্ত)?\s*{WATER}|\b(?:hatu|haatu|hantu)\s*(?:shoman|soman|porjonto|obdi)?\s*{WATER}"
        ),
    ),
    (
        "ankle-deep",
        _c(
            rf"ankle[- ]?(?:deep|high|level)|up to (?:the |their )?ankles?|{NOT_BEFORE}(?:গোড়ালি|গোড়ালি)\s*(?:সমান|পর্যন্ত)?\s*{WATER}|\b(?:gorali|goral|gor?ali)\s*(?:shoman|soman|porjonto|obdi)?\s*{WATER}"
        ),
    ),
]
FIRE_SIZE: list[tuple[str, re.Pattern]] = [
    (
        "large",
        _c(
            r"(?:massive|huge|devastating|major|big|large|raging|terrible|deadly)\s+(?:fire|blaze)|(?:ভয়াবহ|ভয়াবহ|বড়|বড়|ভয়ংকর|ভয়ংকর)\s*(?:আগুন|অগ্নিকাণ্ড)|(?:boro|bhoyabhoho|voyaboho|bhoyonkor)\s+agun"
        ),
    ),
    (
        "small",
        _c(r"(?:minor|small)\s+(?:fire|blaze)|ছোট\s*(?:আগুন|অগ্নিকাণ্ড)|(?:choto|chhoto)\s+agun"),
    ),
]

# --- Cause -------------------------------------------------------------------------------

EN_CUE = r"(?:due to|because of|caused by|after|following|triggered by|owing to|as a result of|from|amid|cause:|cause is|cause was)\s+(?:the\s+|a\s+|an\s+)?(?:\w+\s+){0,2}?"
BN_CUE_AFTER = r"\s*(?:এর|ের|র|er|r)?\s*(?:থাকার|থাকায়|থাকায়|thakar|thakay)?\s*(?:যাওয়ায়|যাওয়ায়|হওয়ায়|হওয়ায়|কারণে|ফলে|জন্য|থেকে|karone|karon|er fole|fole|jonno|theke)"
LABELLED = r"(?:cause|karon|কারণ)\s*[:：]\s*"
# (label, phrase, needs a cue)
CAUSES: list[tuple[str, str, bool]] = [
    (
        "unknown",
        r"(?:cause (?:is |was )?(?:not yet known|unknown|not known|yet to be known))|কারণ\s*(?:জানা যায়নি|জানা যায়নি|অজানা)|karon\s+jana\s+(?:jay ?nai|jayni|jai ?ni)",
        False,
    ),
    (
        "electrical short circuit",
        r"short[- ]?circuit|electrical (?:fault|short)|শর্ট\s*সার্কিট|শর্টসার্কিট|বৈদ্যুতিক\s*ত্রুটি",
        False,
    ),
    (
        "cylinder explosion",
        r"(?:gas\s+)?cylinder\s+(?:explosion|blast|burst|exploded)|সিলিন্ডার\s*(?:বিস্ফোরণ|বিস্ফোরিত)|cylinder\s+(?:bisphoron|bisforon|blast)",
        False,
    ),
    (
        "gas leak",
        r"gas\s+(?:line\s+|pipe(?:line)?\s+)?leak(?:age|ed|ing)?|গ্যাস\s*(?:লাইনের?\s*)?(?:লিক|লিকেজ)|গ্যাসের\s*লিকেজ",
        False,
    ),
    (
        "embankment breach",
        r"embankment\s+(?:breach(?:ed)?|collapse[sd]?|gave way|broke|washed away)|breach(?:es)? in (?:the )?embankment|(?:বেড়ি)?বাঁধ\s*(?:ভেঙে|ভেঙ্গে|ধসে)|(?:bedi\s*)?bandh?\s+(?:bhenge|venge|dhoshe)",
        False,
    ),
    (
        "upstream runoff",
        r"(?:upstream|hill|hilly)\s+(?:runoff|run-off|water|torrents?|onrush)|onrush of (?:water|hill water)|উজানের\s*(?:ঢল|পানি)|পাহাড়ি\s*ঢল|পাহাড়ি\s*ঢল|(?:ujaner|pahari)\s+(?:dhol|pani)",
        False,
    ),
    (
        "vehicle collision",
        r"head[- ]on\s+collision|collision\s+between|collided|rammed|মুখোমুখি\s*সংঘর্ষ|সংঘর্ষে|(?:mukhomukhi\s+)?(?:shongorsho|songhorsho|shongorshe)",
        False,
    ),
    (
        "heavy rain",
        r"heavy\s+(?:[a-z]+\s+)?(?:rain(?:fall|s)?|downpour|showers?)|incessant\s+rain|torrential\s+rain|non-?stop\s+rain|downpours?|(?:ভারী|ভারি|টানা|অতি)\s*(?:বৃষ্টি|বর্ষণ)|অতিবৃষ্টি|(?:bhari|vari|tana|onek)\s+(?:brishti|bristi|bishti)",
        True,
    ),
    (
        "river overflow",
        r"river\s+(?:overflow(?:ed|ing|s)?|swell(?:ed|ing)|burst its banks)|rising\s+(?:river|water level)s?|(?:above|crossed|over)\s+(?:the\s+)?danger\s+(?:level|mark)|নদীর\s*পানি\s*(?:বেড়ে|বৃদ্ধি)|বিপ(?:ৎ|দ)সীমার\s*(?:ওপর|উপর)|nodir\s+pani\s+(?:bere|bariye|briddhi)|bipod\s*shimar\s+(?:upor|opor)",
        True,
    ),
    (
        "blocked drains",
        r"(?:clogged|blocked|choked|poor|inadequate)\s+drain(?:s|age)?|drainage\s+(?:problem|failure|system)|ড্রেন\s*বন্ধ|নালা\s*বন্ধ|ড্রেনেজ\s*(?:ব্যবস্থা|সমস্যা)|drain\s+(?:bondho|bondo|bonddho)",
        True,
    ),
    (
        "protest",
        r"protest(?:ers|s)?|demonstrat(?:ion|ors)|agitation|আন্দোলন|বিক্ষোভ|andolon|bikkhov|bikkhob",
        True,
    ),
    (
        "maintenance work",
        r"repair\s+work|maintenance(?:\s+work)?|construction\s+work|road\s+works?|সংস্কার\s*কাজ|মেরামত|(?:shonskar|songskar)\s+kaj|meramot",
        True,
    ),
]
# A locative ending right after the phrase reads as "because of": বৃষ্টিতে, brishtite.
INSTRUMENTAL = r"(?:তে|ে|য়|য়|te|e)(?![\w\u0980-\u09FF])"

# --- Status ------------------------------------------------------------------------------

STATUS: list[tuple[str, re.Pattern]] = [
    (
        "resolved",
        _c(
            r"water (?:has |had )?(?:receded|gone down|drained|subsided)|(?:fire )?(?:was |has been |had been )?(?:brought under control|extinguished|doused|put out)|(?:brought|got|bring)\s+(?:the\s+)?(?:fire|blaze|flames)\s+under\s+control|(?:road|traffic|movement) (?:has |was )?(?:reopened|resumed|back to normal)|power (?:has been |was )?(?:restored|back)|situation (?:is |has )?(?:returned |back )?(?:to )?normal|পানি\s*নেমে\s*(?:গেছে|গিয়েছে)|নিয়ন্ত্রণে\s*(?:এসেছে|আনা হয়েছে)|নিয়ন্ত্রণে\s*(?:এসেছে|আনা হয়েছে)|আগুন\s*নিভে|স্বাভাবিক\s*হয়েছে|স্বাভাবিক\s*হয়েছে|বিদ্যুৎ\s*ফিরেছে|pani\s+neme\s+(?:gese|geche|gelo)|niyontrone\s+(?:eseche|esheche|ashe|asche)|agun\s+(?:nivse|nibhe|nive)|shobhabik\s+(?:hoise|hoyeche)|current\s+(?:ashse|asche|fire\s+asche)"
        ),
    ),
    (
        "worsening",
        _c(
            r"(?:still\s+|keeps?\s+)?(?:rising|worsening|spreading|getting worse|deteriorating)|বাড়ছে|বাড়ছে|বেড়েই\s*চলেছে|বেড়েই\s*চলেছে|অবনতি|ছড়িয়ে\s*পড়ছে|ছড়িয়ে\s*পড়ছে|barche|bartese|bere\s+(?:jacche|jasse|cholse|choleche)|choriye\s+(?:porche|portese)|kharap\s+hocche"
        ),
    ),
    (
        "improving",
        _c(
            r"receding|(?:water|level)s?\s+(?:is |are )?(?:now |slowly )?(?:going down|falling|dropping)|easing|improving|কমছে|কমতে\s*শুরু|উন্নতি|komche|komtese|kome\s+(?:jacche|jasse)"
        ),
    ),
    (
        "ongoing",
        _c(r"\bstill\b|continues|continuing|remains?\b|এখনও|এখনো|অব্যাহত|\bekhono\b|\bekhno\b"),
    ),
]

# --- Denials -------------------------------------------------------------------------------

EVENT_NOUN = r"(?:fire|flood(?:ing)?|blockade|collapse|accident|explosion|landslide|waterlogging|আগুন|অগ্নিকাণ্ড|বন্যা|অবরোধ|দুর্ঘটনা|ধস|বিস্ফোরণ|জলাবদ্ধতা|agun|bonna|oborodh|durghotona|dhosh)"
DENIAL = _c(
    rf"\brumou?rs?\b|\b(?:is|are|was|were)\s+(?:false|fake|untrue|baseless)\b|fake news|\bhoax\b|baseless|not true|false (?:report|news|claim|information)|did not happen|never happened|no (?:such )?{EVENT_NOUN}\b"
    rf"|গুজব|সত্য\s*নয়|সত্য\s*নয়|মিথ্যা\s*(?:খবর|তথ্য)?|ভুয়া|কোনো\s*{EVENT_NOUN}\s*(?:হয়নি|হয়নি|ঘটেনি|নেই)"
    rf"|\bguj[ou]b\b|\bmitt?ha\b|\b(?:bhua|vua|bhuya)\b|sotti\s+(?:noy|na)|shotti\s+(?:noy|na)|kono\s+{EVENT_NOUN}\s+(?:hoy ?nai|hoyni|ghote ?nai|nai|nei)"
)


# --- Extraction --------------------------------------------------------------------------


def _count(patterns, text: str) -> tuple[int, str, str | None] | None:
    best = None
    for p in patterns:
        for m in p.finditer(text):
            n = as_int(value(m.group("n")))
            if n is None:
                continue
            unit = m.groupdict().get("u")
            if best is None or n > best[0]:
                best = (n, m.group(0), unit)
    return best


def _unit(word: str | None) -> str:
    if word and re.fullmatch(HOUSEHOLDS, word, IC):
        return "households"
    return "people"


def _cause(text: str) -> tuple[str, str] | None:
    found = []
    for label, phrase, needs_cue in CAUSES:
        for m in re.finditer(normalise(phrase), text, IC):
            start, end = m.span()
            before = text[max(0, start - 40) : start]
            after = text[end : end + 25]
            cued = (
                re.search(rf"(?:{EN_CUE})$", before, IC)
                or re.search(rf"{LABELLED}(?:\S+\s+){{0,2}}$", before, IC)
                or re.match(normalise(BN_CUE_AFTER), after, IC)
                or re.match(normalise(INSTRUMENTAL), after, IC)
            )
            if not needs_cue or cued:
                found.append((start, label, m.group(0)))
                break
    if not found:
        return None
    _, label, surface = min(found)
    return label, surface


def extract(text: str) -> list[Claim]:
    """Every detail the text states clearly, one claim per attribute."""
    text = normalise(" ".join(text.split()))
    claims: list[Claim] = []
    if m := DENIAL.search(text):
        claims.append(Claim("occurrence", False, surface=m.group(0)))

    deaths = _count(DEATHS, text)
    if deaths:
        claims.append(Claim("casualty_count", deaths[0], "deaths", deaths[1]))
    else:
        for p in NO_DEATHS:
            if m := p.search(text):
                claims.append(Claim("casualty_count", 0, "deaths", m.group(0)))
                break

    affected = _count(AFFECTED, text)
    if affected:
        claims.append(Claim("affected_count", affected[0], _unit(affected[2]), affected[1]))

    for label, p in [*DEPTH, *FIRE_SIZE]:
        if m := p.search(text):
            claims.append(Claim("magnitude", label, surface=m.group(0)))
            break

    if cause := _cause(text):
        claims.append(Claim("cause", cause[0], surface=cause[1]))

    for label, p in STATUS:
        if m := p.search(text):
            claims.append(Claim("status", label, surface=m.group(0)))
            break
    return claims
