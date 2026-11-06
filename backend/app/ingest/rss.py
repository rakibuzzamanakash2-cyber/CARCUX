"""Any RSS 2.0 or Atom feed, or a Google News sitemap, typically a newspaper.

Only items about a disaster or disruption that name a place in Bangladesh are kept
(see classify.py and places.py). Articles are copyrighted: CARCUX stores the
headline, a short excerpt and the link, never the article itself.
"""

from datetime import UTC, datetime, timedelta, timezone

from defusedxml import ElementTree

from app.ingest.base import Item, Parsed, Request, excerpt, parse_date, plain
from app.ingest.classify import classify
from app.ingest.places import best_place
from app.models.signal import ContentPolicy, Source

ATOM = "{http://www.w3.org/2005/Atom}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}encoded"
DC_DATE = "{http://purl.org/dc/elements/1.1/}date"
SITEMAP = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
NEWS = "{http://www.google.com/schemas/sitemap-news/0.9}"
# How much of the article is read (not stored) when the feed has no summary.
SUMMARY_CHARS = 600
# Older items are left out: some feeds redirect to archives that stopped years ago.
MAX_AGE = timedelta(days=7)


DHAKA = timezone(timedelta(hours=6))


def expand(url: str, now: datetime | None = None) -> str:
    """Fill a dated address: some outlets publish one sitemap per day, e.g.
    .../daily-sitemap/{date}/sitemap.xml, where {date} is today in Dhaka (YYYY-MM-DD)."""
    if "{date}" not in url:
        return url
    today = (now or datetime.now(UTC)).astimezone(DHAKA).date()
    return url.replace("{date}", today.isoformat())


def request(source: Source, _settings) -> Request:
    if not source.url:
        raise ValueError("This source has no feed address")
    return Request(expand(source.url))


def _child(el, *names: str) -> str:
    for name in names:
        found = el.find(name)
        if found is not None:
            # itertext: some feeds put markup inside the title as real elements.
            content = "".join(found.itertext()).strip()
            if content:
                return content
            if found.get("href"):
                return found.get("href").strip()
    return ""


def entries(root) -> list[tuple[str, str, str, str, str]]:
    """(id, title, link, date, summary) for each RSS item, Atom entry or news-sitemap URL.
    A news sitemap has no summary: the headline alone is classified."""
    out = []
    for el in root.iter("item"):
        summary = (plain(_child(el, "description")) or plain(_child(el, CONTENT)))[:SUMMARY_CHARS]
        link = _child(el, "link")
        date = _child(el, "pubDate", DC_DATE)
        out.append((_child(el, "guid") or link, _child(el, "title"), link, date, summary))
    for el in root.iter(f"{ATOM}entry"):
        # Elements without children are falsy, so test for None explicitly.
        link_el = el.find(f"{ATOM}link[@rel='alternate']")
        if link_el is None:
            link_el = el.find(f"{ATOM}link")
        link = link_el.get("href", "") if link_el is not None else ""
        summary = plain(_child(el, f"{ATOM}summary")) or plain(_child(el, f"{ATOM}content"))
        date = _child(el, f"{ATOM}published", f"{ATOM}updated")
        entry_id = _child(el, f"{ATOM}id") or link
        out.append((entry_id, _child(el, f"{ATOM}title"), link, date, summary[:SUMMARY_CHARS]))
    for el in root.iter(f"{SITEMAP}url"):
        news = el.find(f"{NEWS}news")
        if news is None:  # an ordinary sitemap has no headlines: nothing to classify
            continue
        link = _child(el, f"{SITEMAP}loc")
        date = _child(news, f"{NEWS}publication_date") or _child(el, f"{SITEMAP}lastmod")
        out.append((link, _child(news, f"{NEWS}title"), link, date, ""))
    return out


def parse(body: bytes, source: Source, now: datetime | None = None) -> Parsed:
    now = now or datetime.now(UTC)
    root = ElementTree.fromstring(body)
    rows = entries(root)
    items = []
    for guid, raw_title, link, date, summary in rows:
        title = plain(raw_title)
        if not title or not (guid or link):
            continue
        published = parse_date(date) or now
        if published < now - MAX_AGE:
            continue
        kind = classify(title, summary)
        if kind is None:
            continue
        place = best_place(title, summary)
        if place is None:  # not placeable, or not in Bangladesh
            continue
        items.append(
            Item(
                external_id=(guid or link)[:300],
                title=title[:400],
                text=excerpt(summary),
                url=link or None,
                content_policy=ContentPolicy.EXCERPT,
                language=source.language,
                event_type=kind.event_type,
                place_name=place.name,
                district=place.district,
                latitude=place.latitude,
                longitude=place.longitude,
                precision_m=place.precision_m,
                published_at=published,
                extraction={
                    "matched": kind.matched,
                    "matched_in_headline": kind.in_headline,
                    "place_as_written": place.surface,
                    "place_level": place.level,
                    "method": "keywords+gazetteer v1",
                },
            )
        )
    return Parsed(items=items, fetched=len(rows), skipped=len(rows) - len(items))
