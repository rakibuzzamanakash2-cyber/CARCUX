"""GDACS: the Global Disaster Alert and Coordination System (EU JRC and UN OCHA).

Its RSS feed lists current floods, tropical cyclones and earthquakes worldwide, each
with coordinates, a bounding box and a green / orange / red alert level. CARCUX keeps
the items that concern Bangladesh. Licence: CC BY 4.0, credit GDACS.
"""

import math

from defusedxml import ElementTree

from app.ingest.base import Item, Parsed, Request, excerpt, parse_date, plain
from app.ingest.places import best_place
from app.models.signal import ContentPolicy, Severity, Source

NS = {
    "gdacs": "http://www.gdacs.org",
    "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#",
}
EVENT_TYPES = {"FL": "flood", "TC": "cyclone", "EQ": "earthquake"}
SEVERITY = {"green": Severity.MINOR, "orange": Severity.MODERATE, "red": Severity.SEVERE}
# Bangladesh with a margin: cyclones are tracked over the Bay of Bengal.
NEAR_BD = {"lat": (19.0, 27.5), "lon": (87.0, 93.5)}
MAX_PRECISION_M = 300_000


def request(source: Source, _settings) -> Request:
    return Request(source.url or "https://www.gdacs.org/xml/rss.xml")


def _text(el, path: str) -> str:
    found = el.find(path, NS)
    return (found.text or "").strip() if found is not None and found.text else ""


def _precision(bbox: str, lat: float) -> float | None:
    """Half the bounding box diagonal, in metres, capped: how widely the alert applies."""
    try:
        lon_min, lon_max, lat_min, lat_max = (float(v) for v in bbox.split())
    except ValueError:
        return None
    dy = (lat_max - lat_min) / 2 * 110_574
    dx = (lon_max - lon_min) / 2 * 111_320 * math.cos(math.radians(lat))
    return min(math.hypot(dx, dy), MAX_PRECISION_M)


def _concerns_bangladesh(iso3: str, country: str, lat: float | None, lon: float | None) -> bool:
    if "BGD" in iso3.upper() or "bangladesh" in country.lower():
        return True
    return (
        lat is not None
        and lon is not None
        and NEAR_BD["lat"][0] <= lat <= NEAR_BD["lat"][1]
        and NEAR_BD["lon"][0] <= lon <= NEAR_BD["lon"][1]
    )


def parse(body: bytes, source: Source) -> Parsed:
    root = ElementTree.fromstring(body)
    entries = root.findall("./channel/item")
    items: list[Item] = []
    for el in entries:
        kind = _text(el, "gdacs:eventtype").upper()
        event_type = EVENT_TYPES.get(kind)
        lat_s, lon_s = _text(el, "geo:Point/geo:lat"), _text(el, "geo:Point/geo:long")
        lat = float(lat_s) if lat_s else None
        lon = float(lon_s) if lon_s else None
        iso3, country = _text(el, "gdacs:iso3"), _text(el, "gdacs:country")
        if event_type is None or not _concerns_bangladesh(iso3, country, lat, lon):
            continue

        title = plain(_text(el, "title"))
        description = plain(_text(el, "description"))
        guid = _text(el, "guid") or f"{kind}{_text(el, 'gdacs:eventid')}"
        level = _text(el, "gdacs:alertlevel").lower()
        place = best_place(title, description)
        published = parse_date(_text(el, "pubDate")) or parse_date(_text(el, "gdacs:dateadded"))
        if published is None:
            continue
        items.append(
            Item(
                external_id=guid,
                title=title[:400],
                text=excerpt(description),
                url=_text(el, "link") or None,
                content_policy=ContentPolicy.EXCERPT,
                language="en",
                event_type=event_type,
                severity=SEVERITY.get(level),
                place_name=place.name if place else (country or None),
                district=place.district if place else None,
                latitude=lat,
                longitude=lon,
                precision_m=_precision(_text(el, "gdacs:bbox"), lat) if lat is not None else None,
                published_at=published,
                valid_from=parse_date(_text(el, "gdacs:fromdate")),
                valid_until=parse_date(_text(el, "gdacs:todate")),
                extraction={
                    "gdacs_event_id": _text(el, "gdacs:eventid"),
                    "gdacs_episode_id": _text(el, "gdacs:episodeid"),
                    "alert_level": level or None,
                    "countries": country,
                    "credit": "GDACS (CC BY 4.0)",
                },
            )
        )
    return Parsed(items=items, fetched=len(entries), skipped=len(entries) - len(items))
