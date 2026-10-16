"""Bangladeshi places named in text, with coordinates (the dataset's `location_mentions`).

A transparent gazetteer baseline: names of localities, upazilas, districts and divisions
in English, Bangla and common Romanized spellings, matched as people write them:

- Bangla names with case endings: ঢাকায়, ফেনীর, মিরপুরে;
- Banglish names with attached or hyphenated endings: Mirpure, Mirpur-e, Dhakay,
  Feni-te, Fenir (a separate word, "Mirpur e", is matched as the bare name);
- the longest name first, so "Mirpur 10" and "Old Dhaka" win over "Mirpur" and "Dhaka".

The same spelling can name places at several levels or in several districts. The text
decides when it can: a candidate in a district the text also names wins ("Mirpur,
Kushtia"); otherwise the most specific level wins. Precision says how far off the
point may be: a district centre stands for the whole district.
"""

import json
import math
import re
from dataclasses import dataclass, replace
from functools import cache
from importlib.resources import files

# Approximate radius of uncertainty for each level, in metres. Upazilas are placed at
# their district's centre (the source has no upazila coordinates), so district-wide.
PRECISION_M = {"locality": 2_500, "upazila": 30_000, "district": 30_000, "division": 90_000}
RANK = {"locality": 0, "upazila": 1, "district": 2, "division": 3}

# Banglish endings written onto a place name: Mirpure, Mirpur-e, Dhakay, Feni-te.
LATIN_ENDING = r"(?:-?(?:e|te|r|er|y|ye|re|tei|ei)|['’]s)?"  # also the English possessive


@dataclass(frozen=True)
class Place:
    name: str
    level: str  # locality, upazila, district or division
    district: str | None
    division: str | None
    latitude: float
    longitude: float
    precision_m: int
    surface: str  # as written in the text
    start: int = 0  # where in the text
    end: int = 0


@dataclass(frozen=True)
class _Entry:
    name: str
    level: str
    district: str | None
    division: str | None
    lat: float
    lon: float


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@cache
def gazetteer() -> dict:
    data = files(__package__).joinpath("data", "bd_gazetteer.json")
    return json.loads(data.read_text("utf-8"))


@cache
def _index() -> tuple[re.Pattern, dict[str, list[_Entry]]]:
    g = gazetteer()
    districts = {d["name"]: d for d in g["districts"]}
    lookup: dict[str, list[_Entry]] = {}

    def add(names: list[str], entry: _Entry) -> None:
        for n in names:
            entries = lookup.setdefault(n.casefold(), [])
            if all((e.level, e.name, e.district) != (entry.level, entry.name, entry.district)
                   for e in entries):  # fmt: skip
                entries.append(entry)

    for d in g["divisions"]:
        add([d["name"], *d["aliases"], d["bn"]],
            _Entry(d["name"], "division", None, d["name"], d["lat"], d["lon"]))  # fmt: skip
    for d in g["districts"]:
        entry = _Entry(d["name"], "district", d["name"], d["division"], d["lat"], d["lon"])
        add([d["name"], *d["aliases"], d["bn"]], entry)
    for u in g["upazilas"]:
        dist = districts[u["district"]]
        add([u["name"], u["bn"]],
            _Entry(u["name"], "upazila", dist["name"], dist["division"], dist["lat"],
                   dist["lon"]))  # fmt: skip
    for loc in g["localities"]:
        dist = districts[loc["district"]]
        add([loc["name"], *loc["aliases"], loc["bn"]],
            _Entry(loc["name"], "locality", dist["name"], dist["division"], loc["lat"],
                   loc["lon"]))  # fmt: skip

    names = sorted(lookup, key=len, reverse=True)
    latin = "|".join(re.escape(n) for n in names if n.isascii())
    bangla = "|".join(re.escape(n) for n in names if not n.isascii())
    # Latin names stand alone as words (with an optional Banglish ending); Bangla names
    # may carry case endings, so only the start is anchored.
    pattern = re.compile(
        rf"(?<![\w'’])(?P<latin>{latin}){LATIN_ENDING}(?![\w'’])|(?<![ঀ-৿])(?P<bangla>{bangla})",
        re.IGNORECASE,
    )
    return pattern, lookup


def _choose(candidates: list[_Entry], context: set[str]) -> _Entry:
    """A candidate in a district the text names wins; then the most specific level."""
    return min(candidates, key=lambda e: (e.district not in context, RANK[e.level], e.name))


def find_places(text: str) -> list[Place]:
    """Every gazetteer place in the text, in order of appearance (first mention once)."""
    pattern, lookup = _index()
    matches = [(m, lookup[(m.group("latin") or m.group("bangla")).casefold()])
               for m in pattern.finditer(text or "")]  # fmt: skip
    # Districts (and divisions' districts) the text names, to settle ambiguous names.
    context = {e.district for _, cands in matches for e in cands if e.level == "district"}
    seen: set[tuple[str, str, str | None]] = set()
    out = []
    for m, candidates in matches:
        entry = _choose(candidates, context)
        key = (entry.level, entry.name, entry.district)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            Place(
                name=entry.name,
                level=entry.level,
                district=entry.district,
                division=entry.division,
                latitude=entry.lat,
                longitude=entry.lon,
                precision_m=PRECISION_M[entry.level],
                surface=m.group(0),
                start=m.start(),
                end=m.end(),
            )
        )
    return out


def best_place(*texts: str) -> Place | None:
    """Where the item is about, from the first text that names a place (a headline
    before its summary).

    The anchor is the first place mentioned, refined to the most specific place in
    the same district ("Mirpur" over "Dhaka"). If the text also names other districts
    (a bulletin listing several ports), the precision widens to cover them all, so
    the item matches events anywhere in that area.
    """
    for text in texts:
        places = find_places(text or "")
        if not places:
            continue
        first = places[0]
        same_area = [
            p for p in places
            if p.district == first.district and (first.district or p.name == first.name)
        ]  # fmt: skip
        anchor = min(same_area, key=lambda p: RANK[p.level])
        others = [p for p in places if p.district != anchor.district]
        if not others:
            return anchor
        spread_m = max(
            haversine_km(anchor.latitude, anchor.longitude, p.latitude, p.longitude) * 1000
            + p.precision_m
            for p in others
        )
        return replace(anchor, precision_m=int(min(max(anchor.precision_m, spread_m), 300_000)))
    return None


def districts() -> list[dict]:
    """District names, divisions and centres, for pickers."""
    return [
        {"name": d["name"], "division": d["division"], "latitude": d["lat"], "longitude": d["lon"]}
        for d in gazetteer()["districts"]
    ]
