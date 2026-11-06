"""Bangladeshi and international news outlets, and finding a live feed for each.

Feed addresses change and some outlets have none, so each outlet lists the addresses we
know of, and `find_feed` also looks for one:

1. the listed addresses, in order;
2. the feeds the home page announces (<link rel="alternate" type="application/rss+xml">);
3. common feed paths (/feed, /rss.xml, ...);
4. the news sitemaps named in robots.txt (Google News sitemaps list the last two days of
   articles with their headlines, so they work like a feed).

An address is accepted only if it parses and has at least one item from the last week.
`python -m app.cli add-outlets` adds the outlets that are missing and turns on the ones
whose feed works; the rest stay off, with the reason, on the Sources page.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin, urlsplit

from defusedxml import ElementTree

from app.ingest.base import FetchError, Request, parse_date
from app.ingest.rss import entries

FRESH = timedelta(days=7)
COMMON_PATHS = ("/feed", "/feed/", "/rss.xml", "/rss", "/feed/rss.xml", "/rss/rss.xml",
                "/feeds/rss.xml", "/index.xml")  # fmt: skip


@dataclass(frozen=True)
class Outlet:
    key: str
    name: str
    home: str
    language: str  # "bn" or "en"
    feeds: tuple[str, ...] = ()
    interval: int = 30


OUTLETS: tuple[Outlet, ...] = (
    # Already seeded by migration 0005; listed so their addresses can be repaired.
    Outlet("prothomalo-bn", "Prothom Alo", "https://www.prothomalo.com", "bn",
           ("https://www.prothomalo.com/feed/",)),
    Outlet("prothomalo-en", "Prothom Alo English", "https://en.prothomalo.com", "en",
           ("https://en.prothomalo.com/feed/",)),
    Outlet("dailystar", "The Daily Star", "https://www.thedailystar.net", "en",
           ("https://www.thedailystar.net/frontpage/rss.xml",
            "https://www.thedailystar.net/rss.xml"), 60),
    # Bangla
    Outlet("bdnews24-bn", "bdnews24.com (Bangla)", "https://bangla.bdnews24.com", "bn"),
    Outlet("jugantor", "Jugantor", "https://www.jugantor.com", "bn",
           ("https://www.jugantor.com/feed/rss.xml",)),
    Outlet("kalerkantho", "Kaler Kantho", "https://www.kalerkantho.com", "bn",
           ("https://www.kalerkantho.com/rss.xml",)),
    Outlet("jagonews24", "Jago News 24", "https://www.jagonews24.com", "bn",
           ("https://www.jagonews24.com/rss/rss.xml",)),
    Outlet("banglanews24", "Banglanews24", "https://www.banglanews24.com", "bn",
           ("https://www.banglanews24.com/rss/rss.xml",)),
    Outlet("samakal", "Samakal", "https://samakal.com", "bn"),
    Outlet("ittefaq", "The Daily Ittefaq", "https://www.ittefaq.com.bd", "bn"),
    Outlet("banglatribune", "Bangla Tribune", "https://www.banglatribune.com", "bn"),
    Outlet("kalbela", "Kalbela", "https://www.kalbela.com", "bn"),
    Outlet("dhakapost", "Dhaka Post", "https://www.dhakapost.com", "bn"),
    Outlet("risingbd", "Risingbd", "https://www.risingbd.com", "bn"),
    Outlet("somoynews", "Somoy TV", "https://www.somoynews.tv", "bn"),
    Outlet("jamuna", "Jamuna TV", "https://jamuna.tv", "bn"),
    Outlet("bd24live", "BD24Live", "https://www.bd24live.com", "bn",
           ("https://www.bd24live.com/feed",)),
    Outlet("bss", "BSS (national news agency)", "https://www.bssnews.net", "bn"),
    Outlet("bbc-bangla", "BBC News Bangla", "https://www.bbc.com/bengali", "bn",
           ("https://feeds.bbci.co.uk/bengali/rss.xml",), 60),
    # English
    Outlet("bdnews24-en", "bdnews24.com", "https://bdnews24.com", "en",
           ("https://bdnews24.com/?widgetName=rssfeed&widgetId=1150&getXmlFeed=true",)),
    Outlet("dhakatribune", "Dhaka Tribune", "https://www.dhakatribune.com", "en"),
    Outlet("tbsnews", "The Business Standard", "https://www.tbsnews.net", "en"),
    Outlet("newage", "New Age", "https://www.newagebd.net", "en"),
    Outlet("dailysun", "Daily Sun", "https://www.daily-sun.com", "en"),
)  # fmt: skip

SITEMAP_LINE = re.compile(r"^\s*sitemap:\s*(\S+)", re.I | re.M)
ALTERNATE = re.compile(r"<link\b[^>]*\btype=[\"']application/(?:rss|atom)\+xml[\"'][^>]*>", re.I)
HREF = re.compile(r"\bhref=[\"']([^\"']+)[\"']", re.I)


@dataclass
class Found:
    url: str
    items: int
    newest: datetime


def check_feed(url: str, fetcher, now: datetime | None = None) -> Found | None:
    """The feed at `url` if it parses and has an item from the last week."""
    now = now or datetime.now(UTC)
    try:
        body = fetcher(Request(url))
        rows = entries(ElementTree.fromstring(body))
    except (FetchError, ElementTree.ParseError, ValueError, UnicodeError):
        return None

    dates = [d for d in (parse_date(r[3]) for r in rows) if d is not None]
    if not rows or not dates or max(dates) < now - FRESH:
        return None
    return Found(url, len(rows), max(dates))


def _same_site(url: str, home: str) -> bool:
    a, b = urlsplit(url).hostname or "", urlsplit(home).hostname or ""
    base = ".".join(b.split(".")[-2:])
    return a == b or a.endswith("." + base) or a == base


def candidates(outlet: Outlet, fetcher) -> list[str]:
    """Addresses to try, in order, without duplicates."""
    out = list(outlet.feeds)
    try:
        page = fetcher(Request(outlet.home)).decode("utf-8", "replace")
        for tag in ALTERNATE.findall(page):
            m = HREF.search(tag)
            if m:
                out.append(urljoin(outlet.home + "/", m.group(1)))
    except FetchError:
        pass
    root = "{0.scheme}://{0.netloc}".format(urlsplit(outlet.home))
    out += [root + p for p in COMMON_PATHS]
    try:
        robots = fetcher(Request(root + "/robots.txt")).decode("utf-8", "replace")
        maps = SITEMAP_LINE.findall(robots)
        out += [u for u in maps if "news" in u.lower()]
    except FetchError:
        pass
    seen, ordered = set(), []
    for u in out:
        if u not in seen and (u in outlet.feeds or _same_site(u, outlet.home)):
            seen.add(u)
            ordered.append(u)
    return ordered


def find_feed(outlet: Outlet, fetcher, now: datetime | None = None) -> Found | None:
    for url in candidates(outlet, fetcher):
        found = check_feed(url, fetcher, now)
        if found:
            return found
    return None
