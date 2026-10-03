"""ReliefWeb (UN OCHA): situation reports, including republished BMD special weather
bulletins and FFWC flood reports for Bangladesh.

The API needs an approved app name (since 1 November 2025): request one from
ReliefWeb, then set CARCUX_RELIEFWEB_APPNAME and enable the source.
"""

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

from app.ingest.base import Item, Parsed, Request, excerpt, parse_date, plain
from app.ingest.classify import classify
from app.ingest.places import best_place
from app.models.signal import ContentPolicy, Source

DISASTER_TYPES = {
    "flood": "flood",
    "flash flood": "flash_flood",
    "tropical cyclone": "cyclone",
    "storm surge": "storm_surge",
    "land slide": "landslide",
    "landslide": "landslide",
    "mud slide": "landslide",
    "earthquake": "earthquake",
    "fire": "fire",
    "severe local storm": "heavy_rainfall",
}
LOOKBACK = timedelta(days=14)


PAGE_SIZE = 500
MAX_PAGES = 6


def _request(source: Source, settings, conditions: list[dict], offset: int, limit: int) -> Request:
    appname = settings.reliefweb_appname
    if not appname:
        raise ValueError("Set CARCUX_RELIEFWEB_APPNAME to an approved ReliefWeb app name")
    return Request(
        source.url or "https://api.reliefweb.int/v2/reports",
        method="POST",
        params={"appname": appname},
        json={
            "filter": {
                "operator": "AND",
                "conditions": [{"field": "primary_country.iso3", "value": "bgd"}, *conditions],
            },
            "sort": ["date.created:desc"],
            "offset": offset,
            "limit": limit,
            "fields": {
                "include": [
                    "title",
                    "url_alias",
                    "url",
                    "date.created",
                    "date.original",
                    "disaster_type.name",
                    "body",
                    "source.shortname",
                ]
            },
        },
    )


def request(source: Source, settings) -> Request:
    """The latest two weeks, for the scheduled read."""
    since = (datetime.now(UTC) - LOOKBACK).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    return _request(source, settings, [{"field": "date.created", "value": {"from": since}}], 0, 100)


def pages(source: Source, settings, start: date, end: date) -> Iterator[Request]:
    """A past period, by the reports' original publication date."""
    window = {
        "field": "date.original",
        "value": {"from": f"{start.isoformat()}T00:00:00+00:00",
                  "to": f"{end.isoformat()}T23:59:59+00:00"},
    }  # fmt: skip
    for page in range(MAX_PAGES):
        yield _request(source, settings, [window], page * PAGE_SIZE, PAGE_SIZE)


def parse(body: bytes, source: Source) -> Parsed:
    data = json.loads(body).get("data", [])
    items = []
    for row in data:
        f = row.get("fields", {})
        title = plain(f.get("title"))
        text = plain(f.get("body"))[:600]
        types = [d.get("name", "").lower() for d in f.get("disaster_type", [])]
        event_type = next((DISASTER_TYPES[t] for t in types if t in DISASTER_TYPES), None)
        if event_type is None:
            kind = classify(title, text)
            event_type = kind.event_type if kind else None
        dates = f.get("date") or {}
        published = parse_date(dates.get("original")) or parse_date(dates.get("created"))
        if not title or event_type is None or published is None:
            continue
        place = best_place(title, text)
        items.append(
            Item(
                external_id=str(row.get("id")),
                title=title[:400],
                text=excerpt(text),
                url=f.get("url_alias") or f.get("url"),
                content_policy=ContentPolicy.EXCERPT,
                event_type=event_type,
                place_name=place.name if place else "Bangladesh",
                district=place.district if place else None,
                latitude=place.latitude if place else None,
                longitude=place.longitude if place else None,
                precision_m=place.precision_m if place else None,
                published_at=published,
                extraction={
                    "reliefweb_disaster_types": types,
                    "publishers": [s.get("shortname") for s in f.get("source", [])],
                    "place_level": place.level if place else None,
                },
            )
        )
    return Parsed(items=items, fetched=len(data), skipped=len(data) - len(items))
