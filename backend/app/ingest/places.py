"""Find Bangladeshi places named in text and give them coordinates.

A transparent baseline: look up names from a fixed gazetteer (localities, upazilas,
districts, divisions; English and Bangla) and take the most specific one found.
Precision says how far off the point may be: a district centre stands for the
whole district. A learned geoparser (ai/geo/) can replace this later.
"""

import json
import re
from dataclasses import dataclass, replace
from functools import cache
from importlib.resources import files

from app.services.integrity import haversine_km

# Approximate radius of uncertainty for each level, in metres. Upazilas are placed at
# their district's centre (the source has no upazila coordinates), so district-wide.
PRECISION_M = {"locality": 2_500, "upazila": 30_000, "district": 30_000, "division": 90_000}
_RANK = {"locality": 0, "upazila": 1, "district": 2, "division": 3}


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


@dataclass(frozen=True)
class _Entry:
    name: str
    level: str
    district: str | None
    division: str | None
    lat: float
    lon: float


@cache
def gazetteer() -> dict:
    return json.loads(files("app.data").joinpath("bd_gazetteer.json").read_text("utf-8"))


@cache
def _index() -> tuple[re.Pattern, dict[str, _Entry]]:
    g = gazetteer()
    districts = {d["name"]: d for d in g["districts"]}
    lookup: dict[str, _Entry] = {}

    def add(names: list[str], entry: _Entry) -> None:
        for n in names:
            key = n.casefold()
            old = lookup.get(key)
            # The same spelling at two levels: keep the more specific one.
            if old is None or _RANK[entry.level] < _RANK[old.level]:
                lookup[key] = entry

    for d in g["divisions"]:
        entry = _Entry(d["name"], "division", None, d["name"], d["lat"], d["lon"])
        add([d["name"], *d["aliases"], d["bn"]], entry)
    for d in g["districts"]:
        entry = _Entry(d["name"], "district", d["name"], d["division"], d["lat"], d["lon"])
        add([d["name"], *d["aliases"], d["bn"]], entry)
    for u in g["upazilas"]:
        dist = districts[u["district"]]
        entry = _Entry(
            u["name"], "upazila", dist["name"], dist["division"], dist["lat"], dist["lon"]
        )
        add([u["name"], u["bn"]], entry)
    for loc in g["localities"]:
        dist = districts[loc["district"]]
        entry = _Entry(
            loc["name"], "locality", dist["name"], dist["division"], loc["lat"], loc["lon"]
        )
        add([loc["name"], *loc["aliases"], loc["bn"]], entry)

    # Longest names first, so "Mirpur 10" wins over "Mirpur". Latin names must stand
    # alone as words; Bangla names may carry case endings (ঢাকার, ঢাকায়).
    names = sorted(lookup, key=len, reverse=True)
    latin = [re.escape(n) for n in names if n.isascii()]
    bangla = [re.escape(n) for n in names if not n.isascii()]
    pattern = re.compile(
        rf"(?<![\w'’])(?:{'|'.join(latin)})(?![\w'’])|(?<![ঀ-৿])(?:{'|'.join(bangla)})",
        re.IGNORECASE,
    )
    return pattern, lookup


def find_places(text: str) -> list[Place]:
    """Every gazetteer place in the text, in order of appearance (first mention once)."""
    pattern, lookup = _index()
    seen: set[str] = set()
    out = []
    for m in pattern.finditer(text):
        entry = lookup[m.group(0).casefold()]
        if (entry.level, entry.name) in seen:
            continue
        seen.add((entry.level, entry.name))
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
        anchor = min(same_area, key=lambda p: _RANK[p.level])
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
