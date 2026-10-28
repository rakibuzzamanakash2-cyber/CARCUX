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
import gzip
import html as htmllib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from importlib import resources
from pathlib import Path
from urllib.parse import unquote, urlencode, urlsplit, urlunsplit

from carcux_data.j24 import WINDOW
from carcux_data.j24.extract import SCOPE_TERMS
from carcux_data.j24.fetch import Disallowed, Fetcher

CDX = "https://web.archive.org/cdx/search/cdx"
WAYBACK = "https://web.archive.org/web"
BD_TIME = timezone(timedelta(hours=6))
PAGE_SIZE = 1000

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


CHUNK_DAYS = 7  # one index query per week of the window: small answers, kind to the archive


def _chunks(since: str, until: str) -> list[tuple[str, str]]:
    start = date.fromisoformat(since)
    last = date.fromisoformat(until)
    out = []
    while start <= last:
        stop = min(start + timedelta(days=CHUNK_DAYS - 1), last)
        out.append((start.isoformat(), stop.isoformat()))
        start = stop + timedelta(days=1)
    return out


def list_outlet(
    fetcher: Fetcher, outlet: NewsOutlet, since: str, until: str, log: Callable = print
) -> dict[str, str]:
    """{normalised address: first capture timestamp in the window}. Queried week by week and
    page by page; a part the archive does not answer is reported and skipped, and a re-run
    fills it in (answered parts come from the cache)."""
    first: dict[str, str] = {}
    for prefix in outlet.prefixes:
        for lo, hi in _chunks(since, until):
            resume = None
            while True:
                params = [
                    ("url", prefix), ("matchType", "prefix"), ("from", _stamp(lo)),
                    ("to", _stamp(hi, end=True)), ("output", "json"),
                    ("fl", "timestamp,original"), ("filter", "statuscode:200"),
                    ("filter", "mimetype:text/html"), ("collapse", "urlkey"),
                    ("limit", str(PAGE_SIZE)), ("showResumeKey", "true"),
                ]  # fmt: skip
                if outlet.url_regex:
                    params.append(("filter", f"original:.*({outlet.url_regex}).*"))
                if resume:
                    params.append(("resumeKey", resume))
                try:
                    status, _, data = fetcher.get_json(f"{CDX}?{urlencode(params)}")
                except OSError as exc:
                    log(f"  {outlet.key}: no answer for {prefix} {lo} to {hi} ({exc}); "
                        "run news-list again later to fill it in")  # fmt: skip
                    break
                if status != 200 or not isinstance(data, list):
                    log(f"  {outlet.key}: no answer for {prefix} {lo} to {hi} (HTTP {status})")
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


def list_outlet_pages(
    fetcher: Fetcher, outlet: NewsOutlet, since: str, until: str, log: Callable = print
) -> dict[str, str]:
    """Like list_outlet, but reads the archive's index page by page (its paged interface),
    the way the Internet Archive asks large queries to be made. Each page is a fixed slice of
    the index, so no request has to search a whole site's history and time out; the window,
    status and type are applied to each page's rows here. A page that is not answered is
    reported and filled in by a re-run (answered pages come from the cache)."""
    first: dict[str, str] = {}
    lo, hi = _stamp(since), _stamp(until, end=True)
    pattern = re.compile(outlet.url_regex, re.I) if outlet.url_regex else None
    for prefix in outlet.prefixes:
        base = [("url", prefix), ("matchType", "prefix")]
        try:
            status, _, pages = fetcher.get_json(
                f"{CDX}?{urlencode(base + [('showNumPages', 'true')])}"
            )
        except OSError as exc:
            log(f"  {outlet.key}: no page count for {prefix} ({exc}); run again later")
            continue
        if status != 200 or not isinstance(pages, int):
            log(f"  {outlet.key}: no page count for {prefix} (HTTP {status}); run again later")
            continue
        log(f"  {outlet.key}: {prefix} has {pages} index pages")
        missed = 0
        for page in range(pages):
            params = base + [("from", lo), ("to", hi), ("output", "json"),
                             ("fl", "timestamp,original,statuscode,mimetype"),
                             ("page", str(page))]  # fmt: skip
            try:
                status, _, rows = fetcher.get_json(f"{CDX}?{urlencode(params)}")
            except OSError:
                status, rows = 0, None
            if status != 200 or not isinstance(rows, list):
                missed += 1
                continue
            for row in rows:
                if not row or len(row) < 4 or row[0] == "timestamp":
                    continue
                ts, original, code, mime = row[:4]
                if code != "200" or "html" not in (mime or ""):
                    continue
                # Addresses in Bangla script are stored percent-encoded: match the text.
                if pattern and not pattern.search(unquote(original)):
                    continue
                url = normalise(original)
                if url and (url not in first or ts < first[url]):
                    first[url] = ts
            if (page + 1) % 10 == 0:
                log(f"  {outlet.key}: {prefix} page {page + 1} of {pages}, "
                    f"{len(first)} articles so far")  # fmt: skip
        if missed:
            log(f"  {outlet.key}: {missed} of {pages} pages for {prefix} not answered; "
                "run again later to fill them in")  # fmt: skip
    return first


class _Article(HTMLParser):
    """Title, published time, language and text of a news page. Text comes from paragraphs
    when the page has them, else from the article data many sites embed for search engines
    (JSON-LD articleBody) or for their own scripts (Next.js data), else from the page's
    longer visible text blocks (sites that lay articles out without paragraphs)."""

    NOISE = ("nav", "header", "footer", "aside", "form", "button")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.lang: str | None = None
        self.title = ""
        self._in_title = False
        self._in_p = 0
        self._skip = 0
        self._noise = 0
        self.paragraphs: list[str] = []
        self._current: list[str] = []
        self.ld: list[str] = []
        self._json: list[str] = []
        self._in_ld = False
        self._in_json = False
        self.blocks: list[str] = []
        self.times: list[str] = []
        self.canonical = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html" and a.get("lang"):
            self.lang = a["lang"].lower()
        elif tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key and a.get("content"):
                self.meta.setdefault(key, a["content"].strip())
        elif tag == "link" and (a.get("rel") or "").lower() == "canonical" and a.get("href"):
            self.canonical = self.canonical or a["href"]
        elif tag == "title":
            self._in_title = True
        elif tag in ("script", "style", "noscript"):
            kind = (a.get("type") or "").lower()
            if tag == "script" and kind == "application/ld+json":
                self._in_ld = True
            elif tag == "script" and (a.get("id") == "__NEXT_DATA__" or kind == "application/json"):
                self._in_json = True
            else:
                self._skip += 1
        elif tag in self.NOISE:
            self._noise += 1
        elif tag == "p":
            self._in_p += 1
        elif tag == "time" and a.get("datetime"):
            self.times.append(a["datetime"])

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._in_ld:
            self._in_ld = False
        elif tag == "script" and self._in_json:
            self._in_json = False
        elif tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        elif tag in self.NOISE and self._noise:
            self._noise -= 1
        elif tag == "p" and self._in_p:
            self._in_p -= 1
            text = " ".join("".join(self._current).split())
            if text:
                self.paragraphs.append(text)
            self._current = []

    def handle_data(self, data):
        if self._in_ld:
            self.ld.append(data)
        elif self._in_json:
            self._json.append(data)
        elif self._skip:
            return
        elif self._in_title:
            self.title += data
        else:
            if self._in_p:
                self._current.append(data)
            if not self._noise:
                text = " ".join(data.split())
                if len(text) >= 40:
                    self.blocks.append(text)


def _json_objects(chunks: list[str]) -> list:
    out = []
    for chunk in chunks:
        try:
            out.append(json.loads(chunk))
        except ValueError:
            continue
    return out


def _walk(node, found: list, want) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            want(k, v, found)
            _walk(v, found, want)
    elif isinstance(node, list):
        for v in node:
            _walk(v, found, want)


def _ld_fields(page: _Article) -> dict[str, str]:
    """articleBody, headline and datePublished from the page's JSON-LD, if any."""
    fields: dict[str, str] = {}

    def want(k, v, found):
        if k in ("articleBody", "headline", "datePublished") and isinstance(v, str):
            fields.setdefault(k, v.strip())

    for obj in _json_objects(["".join(page.ld)]) + _json_objects(page.ld):
        _walk(obj, [], want)
    return fields


def _script_text(page: _Article) -> str:
    """Sentences held in a page's script data (Next.js and similar): the long strings
    stored under text-like keys, in order."""
    found: list[str] = []

    def want(k, v, out):
        if (
            k in ("text", "body", "content", "paragraph", "value")
            and isinstance(v, str)
            and len(v) >= 40
            and v.count(" ") >= 5
            and not v.startswith(("http", "<"))
        ):
            out.append(" ".join(v.split()))

    for obj in _json_objects(["".join(page._json)]):
        _walk(obj, found, want)
    seen, ordered = set(), []
    for t in found:
        if t not in seen:
            seen.add(t)
            ordered.append(t)
    return " ".join(ordered)


_ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?")

# Dates as Bangladeshi outlets write them. Bangla digits are turned into ASCII first.
_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_MONTHS = {
    **{m: i for i, m in enumerate(("jan feb mar apr may jun jul aug sep oct nov dec").split(), 1)},
    **{m: i for i, m in enumerate(("জানুয়ারি ফেব্রুয়ারি মার্চ এপ্রিল মে জুন জুলাই আগস্ট "
                                   "সেপ্টেম্বর অক্টোবর নভেম্বর ডিসেম্বর").split(), 1)},
}  # fmt: skip
_MONTH_WORD = "|".join(sorted((re.escape(m) for m in _MONTHS), key=len, reverse=True))
_DAY_MONTH_YEAR = re.compile(rf"(?<!\d)(\d{{1,2}})\s+({_MONTH_WORD})[a-z]*\.?,?\s+(\d{{4}})", re.I)
_YMD = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?")
_CLOCK = re.compile(r"(\d{1,2}):(\d{2})\s*(am|pm|এএম|পিএম)?", re.I)
_LABELLED = re.compile(r"(?:প্রকাশ|প্রকাশিত|Published)\s*:\s*(.{6,60})")
_URL_DATE = re.compile(r"/(20\d{2})[/-](\d{2})[/-](\d{2})(?:/|$)")
_EPOCH_MS = re.compile(r'publishedAt"?\s*:\s*"?(1\d{12})"?')
_IMAGE_STAMP = re.compile(r"image-\d+-(1\d{9})\.\w+")


def parse_date(raw: str | None) -> str | None:
    """A published date written in any of the outlets' formats, as ISO ("2024-07-18" or
    "2024-07-18T10:05"). None for a date without a day, or before 2000 (a placeholder)."""
    if not raw:
        return None
    text = raw.translate(_BN_DIGITS)
    if _ISO.match(text):
        return text if text[:4] >= "2000" else None
    m = _YMD.search(text)
    if m:
        y, mo, d, hh, mm = m.groups()
        day = f"{y}-{mo}-{d}"
    else:
        m = _DAY_MONTH_YEAR.search(text)
        if not m:
            return None
        d, word, y = m.groups()
        mo = _MONTHS.get(word.lower()[:3]) or _MONTHS.get(word)
        if not mo:
            return None
        day = f"{y}-{mo:02d}-{int(d):02d}"
        hh = mm = None
        c = _CLOCK.search(text)
        if c:
            h, mm, half = int(c.group(1)), c.group(2), (c.group(3) or "").lower()
            h = h % 12 + 12 if half in ("pm", "পিএম") else (h % 12 if half else h)
            hh = f"{h:02d}"
    try:
        date.fromisoformat(day)
    except ValueError:
        return None
    if day < "2000":
        return None
    return f"{day}T{hh}:{mm}" if hh else day


def _published(page: _Article, html: str) -> tuple[str | None, str | None]:
    """The page's published date and where it came from. In order of trust: the page's
    own date fields; the date in its address; the date printed after "প্রকাশ:" or
    "Published:"; a time stamp in the page's script data; and, last, the upload time
    stamped in the lead image's file name (Jugantor prints no date at all)."""
    ld = re.findall(r'"datePublished"\s*:\s*"([^"]+)"', "".join(page.ld))
    for raw in [page.meta.get(k) for k in ("article:published_time", "og:published_time",
                                           "datepublished", "publishdate", "pubdate",
                                           "dc.date")] + ld + page.times:  # fmt: skip
        found = parse_date(raw)
        if found:
            return found, "page_field"
    for address in (page.meta.get("og:url"), page.canonical):
        m = _URL_DATE.search(unquote(address or ""))
        if m:
            return parse_date("-".join(m.groups())), "address"
    for m in _LABELLED.finditer(re.sub(r"<[^>]+>|&nbsp;", " ", html)):
        found = parse_date(m.group(1))
        if found:
            return found, "page_text"
    m = _EPOCH_MS.search(html)
    if m:
        stamp = datetime.fromtimestamp(int(m.group(1)) / 1000, tz=BD_TIME)
        return stamp.strftime("%Y-%m-%dT%H:%M"), "script_data"
    m = _IMAGE_STAMP.search(page.meta.get("og:image", ""))
    if m:
        stamp = datetime.fromtimestamp(int(m.group(1)), tz=BD_TIME)
        return stamp.strftime("%Y-%m-%dT%H:%M"), "image_stamp"
    return None, None


def _is_article(page: _Article) -> bool:
    """False for a section or front page (its own address has no article number or slug)."""
    address = unquote(page.meta.get("og:url") or page.canonical or "")
    if not address:
        return page.meta.get("og:type", "article") == "article"
    last = urlsplit(address).path.rstrip("/").rsplit("/", 1)[-1]
    return bool(re.search(r"\d{4,}", address)) or last.count("-") >= 3


def _plain(text: str) -> str:
    """Text that may be HTML, escaped once or twice (Kaler Kantho's articleBody)."""
    for _ in range(3):
        unescaped = htmllib.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    return " ".join(re.sub(r"<[^>]+>", " ", text).split())


_JS_STRING = re.compile(r'"((?:[^"\\]|\\.){300,})"')


def _nuxt_text(html: str) -> str:
    """The article body kept in a Nuxt page's state (window.__NUXT__, Somoy): the longest
    string there that holds paragraphs."""
    i = html.find("window.__NUXT__")
    if i < 0:
        return ""
    script = html[i : html.find("</script>", i)]
    best = ""
    for m in _JS_STRING.finditer(script):
        raw = m.group(1)
        if "\\u003Cp" not in raw and "<p" not in raw:
            continue
        try:
            value = json.loads(f'"{raw}"')
        except ValueError:
            continue
        value = _plain(value)
        if len(value) > len(best):
            best = value
    return best


MIN_TEXT = 300  # fewer characters than this from paragraphs: look for the text elsewhere


def read_article(html: bytes, with_text: bool = False) -> dict:
    if html[:2] == b"\x1f\x8b":  # some captures (Ittefaq) were saved still compressed
        try:
            html = gzip.decompress(html)
        except (OSError, EOFError):
            pass
    raw = html.decode("utf-8", "replace")
    page = _Article()
    page.feed(raw)
    ld = _ld_fields(page)
    title = (page.meta.get("og:title") or ld.get("headline")
             or " ".join(page.title.split()))  # fmt: skip
    text, text_source = " ".join(page.paragraphs), "paragraphs"
    if len(text) < MIN_TEXT:
        for source, get in (("json_ld", lambda: _plain(ld.get("articleBody", ""))),
                            ("script_data", lambda: _script_text(page)),
                            ("nuxt_state", lambda: _nuxt_text(raw)),
                            ("text_blocks", lambda: " ".join(page.blocks))):  # fmt: skip
            candidate = get()
            if len(candidate) >= MIN_TEXT:
                text, text_source = " ".join(candidate.split()), source
                break
    low = f"{title} {text[:4000]}".lower()
    terms = sorted({t for t in SCOPE_TERMS if t.lower() in low})
    in_title = any(t.lower() in title.lower() for t in SCOPE_TERMS)
    published, published_source = _published(page, raw)
    extra = {"text": text} if with_text else {}
    return {
        **extra,
        "title": title[:300],
        "published_at": published,
        "published_source": published_source,
        "is_article": _is_article(page),
        "language": page.lang,
        "text_chars": len(text),
        "text_source": text_source,
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
    not_archived: int = 0
    late: int = 0
    skipped: int = 0
    problem: str | None = None


def write_urls(
    out: Path, outlet: NewsOutlet, found: dict[str, str] | list[dict], listed_from: str = "archive"
) -> None:
    """Store an outlet's listed articles, replacing what the same method listed before.
    `found` is {address: capture time} from the archive index, or rows {url, published,
    title} from sitemaps."""
    path = out / "news" / "urls.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    kept = []
    if path.exists():
        for line in path.read_text("utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if not (r["outlet"] == outlet.key and r.get("listed_from", "archive") == listed_from):
                kept.append(line)
    if isinstance(found, dict):
        new = [{"outlet": outlet.key, "url": u, "capture": ts, "listed_from": listed_from}
               for u, ts in sorted(found.items(), key=lambda x: x[1])]  # fmt: skip
    else:
        new = []
        for r in found:
            url = normalise(r["url"])
            if url:
                new.append({"outlet": outlet.key, "url": url, "capture": None,
                            "published": r.get("published"), "title": r.get("title"),
                            "listed_from": listed_from})  # fmt: skip
    rows = [json.dumps(r, ensure_ascii=False) for r in new]
    path.write_text("\n".join(kept + rows) + "\n", encoding="utf-8")


def load_urls(out: Path) -> list[dict]:
    """One row per article: an archive capture time where the index gave one, and the
    published date and title where a sitemap gave them."""
    path = out / "news" / "urls.jsonl"
    if not path.exists():
        return []
    merged: dict[str, dict] = {}
    for line in path.read_text("utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        m = merged.setdefault(r["url"], {"outlet": r["outlet"], "url": r["url"], "capture": None,
                                         "published": None, "title": None})  # fmt: skip
        for key in ("capture", "published", "title"):
            if r.get(key) and not m.get(key):
                m[key] = r[key]
    return list(merged.values())


def day_key(row: dict) -> str | None:
    """YYYYMMDDhhmmss for the window filter: the capture time, else the published date."""
    if row.get("capture"):
        return row["capture"]
    p = row.get("published")
    if p and re.match(r"\d{4}-\d{2}-\d{2}", p):
        return p[:10].replace("-", "") + "120000"
    return None


_CAPTURED = re.compile(r"/web/(\d{14})(?:id_)?/")


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
    only_likely: bool = False,
    log: Callable = print,
) -> list[OutletResult]:
    """Read the listed articles of the given outlets dated between since and until, from the
    archive copy captured then (or nearest to the published date). Articles whose title
    names the uprising are read first; with only_likely, articles whose title does not are
    skipped. Already-read pages come from the cache, so a stopped run resumes."""
    from carcux_data.j24.sitemaps import likely

    lo, hi = _stamp(since), _stamp(until, end=True)
    urls = [u for u in load_urls(out)
            if u["outlet"] in keys and (k := day_key(u)) and lo <= k <= hi]  # fmt: skip
    path = out / "news" / "articles.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    done: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text("utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["url"]] = r
    results = {k: OutletResult(k) for k in keys}
    for u in urls:
        results[u["outlet"]].listed += 1
    order = {True: 0, None: 1, False: 2}
    with path.open("a", encoding="utf-8") as f:
        for key in keys:
            o = outlets[key]
            mine = sorted(
                (u for u in urls if u["outlet"] == key),
                key=lambda u: (order[likely(u.get("title"), u["url"])], day_key(u)),
            )
            if only_likely:
                skipped = [u for u in mine if likely(u.get("title"), u["url"]) is False]
                results[key].skipped = len(skipped)
                mine = [u for u in mine if likely(u.get("title"), u["url"]) is not False]
            if limit:
                mine = mine[:limit]
            for n, u in enumerate(mine, start=1):
                if u["url"] in done:
                    r = done[u["url"]]
                    results[key].fetched += 1
                    results[key].about_uprising += bool(r.get("about_uprising"))
                    continue
                when = u.get("capture") or day_key(u)
                source = (f"{WAYBACK}/{when}id_/{u['url']}" if text_from == "wayback"
                          else u["url"])  # fmt: skip
                try:
                    status, body, final = fetcher.get_page(source)
                except Disallowed:
                    results[key].problem = f"robots.txt disallows {urlsplit(source).netloc}"
                    break
                except OSError as exc:
                    results[key].failed += 1
                    log(f"  {key}: {u['url']} not reachable ({exc})")
                    continue
                if status >= 400 or not body:
                    results[key].failed += 1
                    if status == 404 and text_from == "wayback":
                        results[key].not_archived += 1
                    continue
                art = read_article(body)
                m = _CAPTURED.search(final) if text_from == "wayback" else None
                capture = m.group(1) if m else u.get("capture")
                late = bool(capture and capture[:8] > _late_limit(until))
                record = {
                    "outlet": key, "outlet_name": o.name, "country": o.country,
                    "url": u["url"], "capture": capture, "capture_late": late,
                    "text_from": text_from, **art,
                }  # fmt: skip
                if not record["title"] and u.get("title"):
                    record["title"] = u["title"][:300]
                if not record["published_at"] and u.get("published"):
                    record["published_at"] = u["published"]
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
                done[u["url"]] = record
                results[key].fetched += 1
                results[key].about_uprising += art["about_uprising"]
                results[key].late += late
                if n % 100 == 0:
                    log(f"  {key}: {n} of {len(mine)} read")
    return list(results.values())


LATE_DAYS = 30  # a copy captured more than this long after the window may have been edited


def _late_limit(until: str) -> str:
    return (date.fromisoformat(until) + timedelta(days=LATE_DAYS)).isoformat().replace("-", "")


def capture_day(ts: str) -> str:
    return datetime.strptime(ts[:8], "%Y%m%d").date().isoformat()
