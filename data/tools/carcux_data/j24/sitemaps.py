"""List an outlet's articles from its own sitemaps (the lists sites publish for search
engines): fast, and different outlets can be asked side by side, unlike the Internet
Archive's index, which the trial found too slow and patchy for 42 outlets.

Sitemaps are read with simple patterns, not a full XML parser (no entity expansion, so a
hostile file cannot blow up). Only articles dated inside the window are kept: by the
article's publication date when the sitemap gives one, else its last-modified date, else a
date in its address. Undated articles are counted and left out.
"""

from __future__ import annotations

import gzip
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlsplit

from carcux_data.j24.extract import SCOPE_TERMS
from carcux_data.j24.fetch import Disallowed, Fetcher

COMMON = ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml", "/news-sitemap.xml")
MAX_SITEMAPS = 200  # per outlet; the rest are reported, not read
# Sitemaps whose address names no date are read only while they keep paying off: after
# this many in a row with no article from the window, the rest are left out.
GIVE_UP_AFTER = 25
PROGRESS_EVERY = 25

_BLOCK = re.compile(r"<(url|sitemap)\b[^>]*>(.*?)</\1>", re.S | re.I)
_TAG = {
    "loc": re.compile(r"<loc>\s*(?:<!\[CDATA\[)?\s*(.*?)\s*(?:\]\]>)?\s*</loc>", re.S | re.I),
    "lastmod": re.compile(r"<lastmod>\s*(.*?)\s*</lastmod>", re.S | re.I),
    "published": re.compile(r"<(?:\w+:)?publication_date>\s*(.*?)\s*</", re.S | re.I),
    "title": re.compile(r"<(?:\w+:)?title>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</", re.S | re.I),
}
_DAY = re.compile(r"(20[12]\d)[-/_]?(0[1-9]|1[0-2])[-/_]?(0[1-9]|[12]\d|3[01])(?!\d)")
_MONTH = re.compile(r"(20[12]\d)[-/_](0[1-9]|1[0-2])(?![-/_]?\d)")


def _unescape(s: str) -> str:
    return (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            .replace("&quot;", '"').replace("&#39;", "'").strip())  # fmt: skip


def parse(xml: str) -> tuple[list[dict], list[dict]]:
    """(child sitemaps, urls), each a list of {loc, lastmod, published, title}."""
    children, urls = [], []
    for kind, body in _BLOCK.findall(xml):
        item = {}
        for key, pattern in _TAG.items():
            m = pattern.search(body)
            item[key] = _unescape(m.group(1)) if m else None
        if not item["loc"]:
            continue
        (children if kind.lower() == "sitemap" else urls).append(item)
    return children, urls


def day_of(text: str | None) -> date | None:
    if not text:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", text.strip())
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def dates_in_address(url: str) -> tuple[date, date] | None:
    """The span a sitemap or article address names: a day, or a whole month."""
    path = urlsplit(url).path + "?" + urlsplit(url).query
    m = _DAY.search(path)
    if m:
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return d, d
        except ValueError:
            pass
    m = _MONTH.search(path)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        end = date(y + (mo == 12), mo % 12 + 1, 1)
        return date(y, mo, 1), date.fromordinal(end.toordinal() - 1)
    return None


@dataclass
class Listing:
    rows: list[dict] = field(default_factory=list)
    sitemaps_read: int = 0
    sitemaps_skipped: int = 0
    undated: int = 0
    problem: str | None = None


def _text(fetcher: Fetcher, url: str) -> str | None:
    status, body = fetcher.get_page(url)[:2]
    if status >= 400 or not body:
        return None
    if body[:2] == b"\x1f\x8b":
        try:
            body = gzip.decompress(body)
        except OSError:
            return None
    return body.decode("utf-8", "replace")


def starting_points(fetcher: Fetcher, host: str) -> list[str]:
    """Sitemaps named in robots.txt, else the usual addresses."""
    found = []
    try:
        status, body = fetcher.get_page(f"https://{host}/robots.txt")[:2]
    except Disallowed:
        return []
    if status < 400:
        for line in body.decode("utf-8", "replace").splitlines():
            if line.lower().startswith("sitemap:"):
                found.append(line.split(":", 1)[1].strip())
    return found or [f"https://{host}{p}" for p in COMMON]


def list_from_sitemaps(
    fetcher: Fetcher,
    hosts: list[str],
    since: date,
    until: date,
    *,
    keep: Callable[[str, str | None], bool] = lambda url, title: True,
    log: Callable = print,
) -> Listing:
    out = Listing()
    # Sitemaps whose address names a day or month in the window come first; others (no date
    # in the address) after, and only while they keep yielding articles from the window.
    dated: list[str] = [u for h in hosts for u in starting_points(fetcher, h)]
    other: list[str] = []
    seen: set[str] = set()
    rows: dict[str, dict] = {}
    unproductive = 0
    while dated or other:
        from_other = not dated
        sm = dated.pop(0) if dated else other.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        if out.sitemaps_read >= MAX_SITEMAPS:
            out.sitemaps_skipped += 1 + len(dated) + len(other)
            break
        if from_other and unproductive >= GIVE_UP_AFTER:
            out.sitemaps_skipped += 1 + len(other)
            log(f"  {len(other) + 1} undated sitemaps left out: the last {GIVE_UP_AFTER} "
                "held nothing from the window")  # fmt: skip
            break
        try:
            xml = _text(fetcher, sm)
        except Disallowed:
            out.problem = "robots.txt disallows its sitemaps"
            continue
        except OSError as exc:
            log(f"  sitemap {sm} not reachable ({exc})")
            continue
        out.sitemaps_read += 1
        if out.sitemaps_read % PROGRESS_EVERY == 0:
            log(f"  {out.sitemaps_read} sitemaps read, {len(rows)} articles from the window "
                "so far")  # fmt: skip
        if xml is None:
            continue
        children, urls = parse(xml)
        before = len(rows)
        queued = 0
        for c in children:
            span = dates_in_address(c["loc"])
            if span:
                if span[1] >= since and span[0] <= until:
                    dated.append(c["loc"])
                    queued += 1
                continue
            mod = day_of(c["lastmod"])
            if mod is None or mod >= since:  # may hold articles from the window
                other.append(c["loc"])
                queued += 1
        for u in urls:
            d = day_of(u["published"]) or day_of(u["lastmod"])
            if d is None and (span := dates_in_address(u["loc"])):
                d = span[0] if span[0] == span[1] else None
            if d is None:
                out.undated += 1
                continue
            if not (since <= d <= until):
                continue
            if (urlsplit(u["loc"]).hostname or "").removeprefix("www.") not in hosts:
                continue
            if not keep(u["loc"], u["title"]):
                continue
            rows.setdefault(u["loc"], {
                "url": u["loc"], "published": (u["published"] or u["lastmod"] or d.isoformat()),
                "title": (u["title"] or None) and u["title"][:300],
            })  # fmt: skip
        if from_other:
            unproductive = 0 if (len(rows) > before or queued) else unproductive + 1
    out.rows = list(rows.values())
    return out


def likely(title: str | None) -> bool | None:
    """True when a title names the uprising, False when it does not, None without a title."""
    if not title:
        return None
    low = title.lower()
    return any(t.lower() in low for t in SCOPE_TERMS)
