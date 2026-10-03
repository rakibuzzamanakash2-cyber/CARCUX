"""Decide whether a news item is about a disaster or disruption, and which kind.

A transparent keyword baseline in English and Bangla, so every decision can be
explained ("matched 'waterlogging' in the headline"). It is deliberately strict:
an item needs a match in its headline, or two in its summary. The learned
classifier (ai/classify/) replaces this and is evaluated against analyst labels.
"""

import re
from dataclasses import dataclass

# event_type -> patterns. English patterns are matched as whole words, ignoring case.
_EN: dict[str, list[str]] = {
    "flash_flood": [r"flash floods?", r"hill(?:y)? (?:torrent|run-?off)s?"],
    "flood": [r"flood(?:s|ed|ing|water|waters)?", r"inundat(?:ed|ion|es)", r"deluge"],
    "waterlogging": [r"water-?logg(?:ed|ing)", r"water-?log"],
    "storm_surge": [r"storm surges?", r"tidal surges?"],
    "cyclone": [
        r"cyclon(?:e|es|ic)",
        r"tropical storm",
        r"deep depression",
        r"(?:danger|cautionary|warning) signal(?: no\.?)? ?\d*",
    ],
    "landslide": [r"landslides?", r"landslips?", r"hill collapses?", r"mudslides?"],
    "river_erosion": [r"river(?:bank)? erosion", r"erosion"],
    "heavy_rainfall": [
        r"heavy rain(?:fall|s)?",
        r"torrential rain",
        r"downpours?",
        r"incessant rain",
    ],
    "earthquake": [r"earthquakes?", r"tremors?", r"quake"],
    "road_blockage": [
        r"road blockades?",
        r"blockaded?",
        r"blocked (?:the )?(?:road|highway)",
        r"(?:road|highway)s? (?:remain(?:s|ed)? )?blocked",
        r"(?:traffic|vehicular movement|vehicle movement) (?:halted|suspended|disrupted)",
        r"tailbacks?",
    ],
    "road_accident": [
        r"road (?:accident|crash)(?:es|s)?",
        r"bus (?:plunge|crash|accident)s?",
        r"(?:truck|bus|car|microbus|motorcycle) (?:collision|crash)",
        r"run over",
    ],
    "bridge_damage": [r"bridge (?:collapse[sd]?|washed away|damaged)", r"culvert collapse[sd]?"],
    "power_outage": [r"power outages?", r"blackouts?", r"load-?shedding", r"power cuts?"],
    "gas_outage": [r"gas (?:crisis|shortage)", r"gas supply (?:suspended|disrupted|cut)"],
    "water_outage": [r"water (?:crisis|shortage)", r"water supply (?:suspended|disrupted|cut)"],
    "rail_accident": [r"derail(?:ed|ment|s)?", r"train (?:collision|accident|crash)"],
    "fire": [
        r"fire broke out",
        r"caught fire",
        r"blaze",
        r"gutted",
        r"firefighters?",
        r"fire service and civil defence",
        r"(?:massive|devastating|deadly) fire",
        r"fire (?:at|in|on) (?:a |the )?\w+",
    ],
    "building_collapse": [
        r"building collapses?",
        r"(?:roof|wall) collapse[sd]?",
        r"collapsed building",
    ],
    "explosion": [r"explosions?", r"blast(?! furnace)", r"cylinder (?:burst|explosion)"],
}

# Bangla matches as substrings: words take case endings (বন্যায়, বন্যার).
_BN: dict[str, list[str]] = {
    "flash_flood": ["আকস্মিক বন্যা", "পাহাড়ি ঢল", "ঢলে"],
    "flood": ["বন্যা", "বানের পানি", "প্লাবিত"],
    "waterlogging": ["জলাবদ্ধতা", "জলজট"],
    "storm_surge": ["জলোচ্ছ্বাস"],
    "cyclone": ["ঘূর্ণিঝড়", "সতর্কসংকেত", "বিপৎসংকেত", "নিম্নচাপ"],
    "landslide": ["ভূমিধস", "পাহাড়ধস", "পাহাড় ধস"],
    "river_erosion": ["নদীভাঙন", "নদী ভাঙন", "ভাঙনে"],
    "heavy_rainfall": ["ভারী বর্ষণ", "ভারী বৃষ্টি", "অতিবৃষ্টি", "টানা বৃষ্টি"],
    "earthquake": ["ভূমিকম্প"],
    "road_blockage": ["সড়ক অবরোধ", "অবরোধ", "যান চলাচল বন্ধ", "যানজট"],
    "road_accident": ["সড়ক দুর্ঘটনা", "বাস খাদে", "মুখোমুখি সংঘর্ষ"],
    "bridge_damage": ["সেতু ধস", "সেতু ভেঙে", "কালভার্ট ধস"],
    "power_outage": ["লোডশেডিং", "বিদ্যুৎ বিভ্রাট", "বিদ্যুৎহীন"],
    "gas_outage": ["গ্যাস সংকট", "গ্যাস সরবরাহ বন্ধ"],
    "water_outage": ["পানি সংকট", "পানি সরবরাহ বন্ধ"],
    "rail_accident": ["লাইনচ্যুত", "ট্রেন দুর্ঘটনা"],
    "fire": ["অগ্নিকাণ্ড", "আগুন"],
    "building_collapse": ["ভবন ধস", "ভবন ধসে", "ছাদ ধসে"],
    "explosion": ["বিস্ফোরণ"],
}

_PATTERNS: dict[str, re.Pattern] = {
    etype: re.compile(
        "|".join(
            [rf"(?<!\w)(?:{p})(?!\w)" for p in _EN.get(etype, [])]
            + [re.escape(w) for w in _BN.get(etype, [])]
        ),
        re.IGNORECASE,
    )
    for etype in {*_EN, *_BN}
}

# More specific types win over the general ones they overlap with.
_SPECIFIC_FIRST = ["flash_flood", "waterlogging", "storm_surge", "rail_accident", "bridge_damage"]


@dataclass(frozen=True)
class Classification:
    event_type: str
    matched: list[str]  # the words that decided it, for the explanation
    in_headline: bool


def classify(headline: str, summary: str = "") -> Classification | None:
    """The best-matching event type, or None if this is not about a disruption."""
    scores: dict[str, tuple[int, list[str], bool]] = {}
    for etype, pattern in _PATTERNS.items():
        head = [m.group(0) for m in pattern.finditer(headline or "")]
        body = [m.group(0) for m in pattern.finditer(summary or "")]
        if head or len(body) >= 2:
            scores[etype] = (3 * len(head) + len(body), head + body, bool(head))
    if not scores:
        return None
    for etype in _SPECIFIC_FIRST:
        if etype in scores and scores[etype][2]:
            score, matched, head = scores[etype]
            return Classification(etype, _unique(matched), head)
    etype = max(scores, key=lambda k: (scores[k][2], scores[k][0]))
    score, matched, head = scores[etype]
    return Classification(etype, _unique(matched), head)


def _unique(words: list[str]) -> list[str]:
    return list(dict.fromkeys(w.lower() for w in words))[:5]
