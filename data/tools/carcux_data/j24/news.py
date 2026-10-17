"""Collect what outlets published in the window, as it was at the time (protocol, "Items").

Two stages, so the volume is known before anything heavy runs:

1. `list_outlet`: ask the Internet Archive's CDX index which article addresses under each
   outlet's sections were captured inside the window (one request per 5,000 addresses).
2. `fetch_articles`: read each article from its first capture in the window (or, with
   `text_from="live"`, from the outlet itself), keep the title, the published time the page
   states, its language, and whether it is about the uprising.

Outputs, in the folder given with --out (working files, never published as they are):

    news/urls.jsonl       every captured article address, with its first capture time
    news/articles.jsonl   per fetched article: outlet, link, capture and published time,
                          language, title, and the uprising hint
    cache/pages/          the pages themselves, compressed, for matching to claims later
"""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from importlib import resources
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit

from carcux_data.j24 import WINDOW
from carcux_data.j24.extract import SCOPE_TERMS
from carcux_data.j24.fetch import Disallowed, Fetcher

CDX = "https://web.archive.org/cdx/search/cdx"
WAYBACK = "https://web.archive.org/web"
PAGE_SIZE = 5000

# Addresses that are listings, media or tools, not articles.
NOT_ARTICLE = re.compile(
    r"/(tag|tags|topic|topics|author|authors|archive|search|category|categories|photo|photos|"
    r"gallery|galleries|login|subscribe|rss|feed|amp-stories|page)(/|$)"
    r"|\.(jpg|jpeg|png|gif|webp|svg|css|js|pdf|xml|json|mp4|mp3)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NewsOutlet:
    key: str
    name: str
    country: str
    language: str
    prefixes: tuple[str, ...]
    url_regex: str | None


def load_news_outlets() -> dict[str, NewsOutlet]:
    text = resources.files("carcux_data.j24").joinpath("news_outlets.csv").read_text("utf-8")
    out = {}
    for r in csv.DictReader(text.splitlines()):
        out[r["key"]] = NewsOutlet(
            r["key"], r["name"], r["country"], r["language"],
            tuple(p for p in r["prefixes"].split(";") if p), r["url_regex"] or None,
        )  # fmt: skip
    return out


def normalise(url: str) -> str | None:
    """One address per article: https, no query or fragment, no AMP or trailing slash.
    None for addresses that are not articles."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    host = parts.netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/amp(/|$)", "/", parts.path).rstrip("/")
    if path.endswith("/amp"):
        path = path[:-4]
    if path.count("/") < 2 and not re.search(r"\d{4,}", path):
        return None  # a section front page, not an article
    if NOT_ARTICLE.search(path):
        return None
    return urlunsplit(("https", host, path, "", ""))


def _stamp(day: str, end: bool = False) -> str:
    return day.replace("-", "") + ("235959" if end else "000000")


def list_outlet(
    fetcher: Fetcher, outlet: NewsOutlet, since: str, until: str, log: Callable = print
) -> dict[str, str]:
    """{normalised address: first capture timestamp in the window}."""
    first: dict[str, str] = {}
    for prefix in outlet.prefixes:
        resume = None
        while True:
            params = [
                ("url", prefix), ("matchType", "prefix"), ("from", _stamp(since)),
                ("to", _stamp(until, end=True)), ("output", "json"),
                ("fl", "timestamp,original"), ("filter", "statuscode:200"),
                ("filter", "mimetype:text/html"), ("collapse", "urlkey"),
                ("limit", str(PAGE_SIZE)), ("showResumeKey", "true"),
            ]  # fmt: skip
            if outlet.url_regex:
                params.append(("filter", f"original:.*({outlet.url_regex}).*"))
            if resume:
                params.append(("resumeKey", resume))
            status, _, data = fetcher.get_json(f"{CDX}?{urlencode(params)}")
            if status != 200 or not isinstance(data, list):
                log(f"  {outlet.key}: the archive index did not answer for {prefix} "
                    f"(HTTP {status})")  # fmt: skip
                break
            rows = data[1:] if data and data[0] == ["timestamp", "original"] else data
            resume = None
            for row in rows:
                if not row:
                    continue
                if len(row) == 1:  # the resume key, after an empty row
                    resume = row[0]
                    continue
                ts, original = row[0], row[1]
                url = normalise(original)
                if url and (url not in first or ts < first[url]):
                    first[url] = ts
            if not resume:
                break
    return first


class _Article(HTMLParser):
    """Title, published time, language and paragraph text of a news page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.lang: str | None = None
        self.title = ""
        self._in_title = False
        self._in_p = 0
        self._skip = 0
        self.paragraphs: list[str] = []
        self._current: list[str] = []
        self.ld: list[str] = []
        self._in_ld = False
        self.times: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html" and a.get("lang"):
            self.lang = a["lang"].lower()
        elif tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key and a.get("content"):
                self.meta.setdefault(key, a["content"].strip())
        elif tag == "title":
            self._in_title = True
        elif tag in ("script", "style", "noscript"):
            if tag == "script" and (a.get("type") or "").lower() == "application/ld+json":
                self._in_ld = True
            else:
                self._skip += 1
        elif tag == "p":
            self._in_p += 1
        elif tag == "time" and a.get("datetime"):
            self.times.append(a["datetime"])

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._in_ld:
            self._in_ld = False
        elif tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        elif tag == "p" and self._in_p:
            self._in_p -= 1
            text = " ".join("".join(self._current).split())
            if text:
                self.paragraphs.append(text)
            self._current = []

    def handle_data(self, data):
        if self._in_ld:
            self.ld.append(data)
        elif self._skip:
            return
        elif self._in_title:
            self.title += data
        elif self._in_p:
            self._current.append(data)


_ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?")


def _published(page: _Article) -> str | None:
    for key in ("article:published_time", "og:published_time", "datepublished",
                "publishdate", "pubdate", "dc.date"):  # fmt: skip
        if page.meta.get(key) and _ISO.match(page.meta[key]):
            return page.meta[key]
    m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', "".join(page.ld))
    if m and _ISO.match(m.group(1)):
        return m.group(1)
    return next((t for t in page.times if _ISO.match(t)), None)


def read_article(html: bytes) -> dict:
    page = _Article()
    page.feed(html.decode("utf-8", "replace"))
    title = page.meta.get("og:title") or " ".join(page.title.split())
    text = " ".join(page.paragraphs)
    low = f"{title} {text[:4000]}".lower()
    terms = sorted({t for t in SCOPE_TERMS if t.lower() in low})
    in_title = any(t.lower() in title.lower() for t in SCOPE_TERMS)
    return {
        "title": title[:300],
        "published_at": _published(page),
        "language": page.lang,
        "text_chars": len(text),
        "scope_terms": terms,
        "about_uprising": in_title or len(terms) >= 2,
    }


@dataclass
class OutletResult:
    outlet: str
    listed: int = 0
    fetched: int = 0
    about_uprising: int = 0
    failed: int = 0
    problem: str | None = None


def write_urls(out: Path, outlet: NewsOutlet, first: dict[str, str]) -> None:
    path = out / "news" / "urls.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    kept = []
    if path.exists():
        kept = [line for line in path.read_text("utf-8").splitlines()
                if line.strip() and json.loads(line)["outlet"] != outlet.key]  # fmt: skip
    rows = [json.dumps({"outlet": outlet.key, "url": u, "capture": ts}) for u, ts in
            sorted(first.items(), key=lambda x: x[1])]  # fmt: skip
    path.write_text("\n".join(kept + rows) + "\n", encoding="utf-8")


def load_urls(out: Path) -> list[dict]:
    path = out / "news" / "urls.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def fetch_articles(
    fetcher: Fetcher,
    out: Path,
    outlets: dict[str, NewsOutlet],
    *,
    keys: list[str],
    since: str = WINDOW[0],
    until: str = WINDOW[1],
    limit: int | None = None,
    text_from: str = "wayback",
    log: Callable = print,
) -> list[OutletResult]:
    """Read the listed articles of the given outlets captured between since and until.
    Already-read pages come from the cache, so a stopped run resumes where it stopped."""
    lo, hi = _stamp(since), _stamp(until, end=True)
    urls = [u for u in load_urls(out) if u["outlet"] in keys and lo <= u["capture"] <= hi]
    path = out / "news" / "articles.jsonl"
    done: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text("utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["url"]] = r
    results = {k: OutletResult(k) for k in keys}
    for u in urls:
        results[u["outlet"]].listed += 1
    with path.open("a", encoding="utf-8") as f:
        for key in keys:
            o = outlets[key]
            mine = [u for u in urls if u["outlet"] == key]
            if limit:
                mine = mine[:limit]
            for n, u in enumerate(mine, start=1):
                if u["url"] in done:
                    r = done[u["url"]]
                    results[key].fetched += 1
                    results[key].about_uprising += bool(r.get("about_uprising"))
                    continue
                source = (f"{WAYBACK}/{u['capture']}id_/{u['url']}" if text_from == "wayback"
                          else u["url"])  # fmt: skip
                try:
                    status, body = fetcher.get_page(source)
                except Disallowed:
                    results[key].problem = f"robots.txt disallows {urlsplit(source).netloc}"
                    break
                except OSError as exc:
                    results[key].failed += 1
                    log(f"  {key}: {u['url']} not reachable ({exc})")
                    continue
                if status >= 400 or not body:
                    results[key].failed += 1
                    continue
                art = read_article(body)
                record = {
                    "outlet": key, "outlet_name": o.name, "country": o.country,
                    "url": u["url"], "capture": u["capture"], "text_from": text_from,
                    **art,
                }  # fmt: skip
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
                done[u["url"]] = record
                results[key].fetched += 1
                results[key].about_uprising += art["about_uprising"]
                if n % 100 == 0:
                    log(f"  {key}: {n} of {len(mine)} read")
    return list(results.values())


def capture_day(ts: str) -> str:
    return datetime.strptime(ts[:8], "%Y%m%d").date().isoformat()
