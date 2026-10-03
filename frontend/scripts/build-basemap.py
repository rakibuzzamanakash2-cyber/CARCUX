"""Build the console's offline basemap (public/geo/bangladesh.json) from Natural Earth.

Natural Earth is public domain (https://www.naturalearthdata.com). The output is a
small GeoJSON with Bangladesh, its divisions, neighbouring land, major rivers and
cities, so the situation map works without any tile server or internet access.

    pip install shapely
    python scripts/build-basemap.py /path/to/natural-earth-geojson-dir

Needs ne_10m_admin_0_countries, ne_10m_admin_1_states_provinces,
ne_10m_rivers_lake_centerlines and ne_10m_populated_places_simple (.geojson), from
https://github.com/nvkelso/natural-earth-vector/tree/master/geojson
"""

import json
import math
import sys
from pathlib import Path

from shapely.geometry import box, mapping, shape

SRC = Path(sys.argv[1])
OUT = Path(__file__).resolve().parents[1] / "public" / "geo" / "bangladesh.json"
FRAME = box(86.0, 19.6, 94.8, 27.8)  # a little beyond Bangladesh, for context
TOLERANCE = 0.004  # degrees, about 400 m


def features(name: str) -> list[dict]:
    return json.loads((SRC / f"{name}.geojson").read_text(encoding="utf-8"))["features"]


def rounded(geom: dict) -> dict:
    def r(c):
        return [round(c[0], 4), round(c[1], 4)] if isinstance(c[0], float) else [r(x) for x in c]

    return {"type": geom["type"], "coordinates": r(geom["coordinates"])}


def clip(geom, simplify=True):
    g = shape(geom).intersection(FRAME)
    if g.is_empty:
        return None
    if simplify:
        g = g.simplify(TOLERANCE, preserve_topology=True)
    return rounded(mapping(g))


out = []
for f in features("ne_10m_admin_0_countries"):
    name = f["properties"]["ADMIN"]
    g = clip(f["geometry"])
    if g:
        kind = "country" if name == "Bangladesh" else "neighbour"
        out.append({"type": "Feature", "properties": {"kind": kind, "name": name}, "geometry": g})

for f in features("ne_10m_admin_1_states_provinces"):
    if f["properties"].get("admin") == "Bangladesh":
        g = clip(f["geometry"])
        name = f["properties"]["name"].replace("Chittagong", "Chattogram").replace(
            "Barisal", "Barishal"
        )
        out.append({"type": "Feature", "properties": {"kind": "division", "name": name}, "geometry": g})

for f in features("ne_10m_rivers_lake_centerlines"):
    if f["properties"].get("scalerank", 99) <= 8:
        g = clip(f["geometry"])
        if g:
            props = {"kind": "river", "name": f["properties"].get("name")}
            out.append({"type": "Feature", "properties": props, "geometry": g})

for f in features("ne_10m_populated_places_simple"):
    p = f["properties"]
    if p.get("adm0name") == "Bangladesh" and p["scalerank"] <= 8:
        props = {"kind": "city", "name": p["name"], "rank": p["scalerank"]}
        out.append({"type": "Feature", "properties": props, "geometry": rounded(f["geometry"])})

OUT.write_text(
    json.dumps({"type": "FeatureCollection", "features": out}, separators=(",", ":")),
    encoding="utf-8",
)
print(f"{OUT} {OUT.stat().st_size // 1024} KB, {len(out)} features")

# A decorative outline for the sign-in page (drawn on the forest-green panel):
# Bangladesh, its rivers and divisions.
W, LON0, LON1, LAT0, LAT1 = 600, 87.9, 92.8, 20.5, 26.75
K = math.cos(math.radians(23.7))
H = round(W * (LAT1 - LAT0) / ((LON1 - LON0) * K))


def xy(c):
    return f"{(c[0] - LON0) / (LON1 - LON0) * W:.1f},{(LAT1 - c[1]) / (LAT1 - LAT0) * H:.1f}"


def rings(geom):
    t, cs = geom["type"], geom["coordinates"]
    if t == "Polygon":
        return cs
    if t == "MultiPolygon":
        return [r for poly in cs for r in poly]
    if t == "LineString":
        return [cs]
    if t == "MultiLineString":
        return cs
    return []


def path(geom, close):
    return " ".join(
        "M" + " L".join(xy(c) for c in ring) + (" Z" if close else "") for ring in rings(geom)
    )


parts = []
for f in out:
    k = f["properties"]["kind"]
    if k == "country":
        parts.append(f'<path d="{path(f["geometry"], True)}" fill="#145236" stroke="#3a8a5e" stroke-width="1.2"/>')
for f in out:
    k = f["properties"]["kind"]
    if k == "division":
        parts.append(f'<path d="{path(f["geometry"], True)}" fill="none" stroke="#2c6e4a" stroke-width="0.8" stroke-dasharray="3 4"/>')
    elif k == "river":
        parts.append(f'<path d="{path(f["geometry"], False)}" fill="none" stroke="#6fbf95" stroke-width="1.4"/>')
svg = (
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
    f'<defs><clipPath id="bd"><rect width="{W}" height="{H}"/></clipPath></defs>'
    f'<g clip-path="url(#bd)">{"".join(parts)}</g></svg>'
)
SVG = OUT.with_name("bangladesh-outline.svg")
SVG.write_text(svg, encoding="utf-8")
print(f"{SVG} {SVG.stat().st_size // 1024} KB, {W}x{H}")
