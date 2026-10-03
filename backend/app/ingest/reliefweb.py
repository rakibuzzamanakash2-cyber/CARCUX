"""ReliefWeb (UN OCHA): situation reports, including republished BMD special weather
bulletins and FFWC flood reports for Bangladesh.

The API needs an approved app name (since 1 November 2025): request one from
ReliefWeb, then set CARCUX_RELIEFWEB_APPNAME and enable the source.
"""

import json
from datetime import UTC, datetime, timedelta

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


def request(source: Source, settings) -> Request:
    appname = settings.reliefweb_appname
    if not appname:
        raise ValueError("Set CARCUX_RELIEFWEB_APPNAME to an approved ReliefWeb app name")
    since = (datetime.now(UTC) - LOOKBACK).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    return Request(
        source.url or "https://api.reliefweb.int/v2/reports",
        method="POST",
        params={"appname": appname},
        json={
            "filter": {
                "operator": "AND",
                "conditions": [
                    {"field": "primary_country.iso3", "value": "bgd"},
                    {"field": "date.created", "value": {"from": since}},
                ],
            },
            "sort": ["date.created:desc"],
            "limit": 100,
            "fields": {
                "include": [
                    "title",
                    "url_alias",
                    "url",
                    "date.created",
                    "disaster_type.name",
                    "body",
                    "source.shortname",
                ]
            },
        },
    )


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
        published = parse_date((f.get("date") or {}).get("created"))
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
