"""GDACS event archive: past floods, tropical cyclones and earthquakes, for backfilling.

The live feed (gdacs.py) only lists current alerts. The search API returns events in a
date range as GeoJSON, at most 100 per page. External ids match the live feed's
("FL1104200"), so an event read both ways is stored once.

    https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH
        ?eventlist=FL;TC;EQ&fromdate=2024-08-01&todate=2024-09-15&pagenumber=1
"""

import json
import math
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

from app.ingest.base import Item, Parsed, Request, excerpt, plain
from app.ingest.gdacs import EVENT_TYPES, MAX_PRECISION_M, NEAR_BD, SEVERITY
from app.ingest.places import best_place
from app.models.signal import ContentPolicy, Source

SEARCH_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
PAGE_SIZE = 100  # the API's maximum
MAX_PAGES = 20


def pages(source: Source, _settings, start: date, end: date) -> Iterator[Request]:
    for page in range(1, MAX_PAGES + 1):
        yield Request(
            SEARCH_URL,
            params={
                "eventlist": "FL;TC;EQ",
                "fromdate": start.isoformat(),
                "todate": end.isoformat(),
                "pagenumber": str(page),
            },
        )


def _date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)  # GDACS times are UTC


def _countries(p: dict) -> tuple[str, str]:
    iso3 = [str(p.get("iso3") or "")]
    names = [str(p.get("country") or "")]
    for c in p.get("affectedcountries") or []:
        if isinstance(c, dict):
            iso3.append(str(c.get("iso3") or ""))
            names.append(str(c.get("countryname") or ""))
    return ",".join(i for i in iso3 if i), ", ".join(dict.fromkeys(n for n in names if n))


def _precision(bbox: Any, lat: float) -> float | None:
    """Half the bounding box diagonal ([minlon, minlat, maxlon, maxlat]), capped."""
    if not isinstance(bbox, list) or len(bbox) != 4:
        return None
    try:
        lon_min, lat_min, lon_max, lat_max = (float(v) for v in bbox)
    except (TypeError, ValueError):
        return None
    dy = (lat_max - lat_min) / 2 * 110_574
    dx = (lon_max - lon_min) / 2 * 111_320 * math.cos(math.radians(lat))
    return min(math.hypot(dx, dy), MAX_PRECISION_M) or None


def parse(body: bytes, source: Source) -> Parsed:
    data = json.loads(body) if body.strip() else {}
    features = data.get("features") or []
    items: list[Item] = []
    for f in features:
        p = f.get("properties") or {}
        kind = str(p.get("eventtype") or "").upper()
        event_type = EVENT_TYPES.get(kind)
        coords = (f.get("geometry") or {}).get("coordinates") or []
        lon, lat = (float(coords[0]), float(coords[1])) if len(coords) >= 2 else (None, None)
        iso3, countries = _countries(p)
        near = (
            lat is not None
            and NEAR_BD["lat"][0] <= lat <= NEAR_BD["lat"][1]
            and NEAR_BD["lon"][0] <= lon <= NEAR_BD["lon"][1]
        )
        if event_type is None or not ("BGD" in iso3.upper() or "Bangladesh" in countries or near):
            continue
        start = _date(p.get("fromdate"))
        if start is None:
            continue
        title = plain(p.get("name") or p.get("description") or f"{kind} event")
        description = plain(p.get("htmldescription") or p.get("description") or "")
        url = p.get("url")
        report_url = url.get("report") if isinstance(url, dict) else url
        level = str(p.get("alertlevel") or "").lower()
        place = best_place(title, description)
        items.append(
            Item(
                external_id=f"{kind}{p.get('eventid')}",
                title=title[:400],
                text=excerpt(description) if description and description != title else None,
                url=str(report_url) if report_url else None,
                content_policy=ContentPolicy.EXCERPT,
                event_type=event_type,
                severity=SEVERITY.get(level),
                place_name=place.name if place else (countries or None),
                district=place.district if place else None,
                latitude=lat,
                longitude=lon,
                precision_m=_precision(f.get("bbox"), lat) if lat is not None else None,
                published_at=start,
                valid_from=start,
                valid_until=_date(p.get("todate")),
                extraction={
                    "gdacs_event_id": str(p.get("eventid") or ""),
                    "gdacs_episode_id": str(p.get("episodeid") or ""),
                    "alert_level": level or None,
                    "countries": countries,
                    "credit": "GDACS (CC BY 4.0)",
                    "method": "GDACS archive search",
                },
            )
        )
    return Parsed(items=items, fetched=len(features), skipped=len(features) - len(items))
