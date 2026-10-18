"""Find how each outlet lists its articles by date, before building a lister for it.

For each outlet, a handful of common date-listing addresses are tried for two days in the
window (an archive page, a year/month/day path, a WordPress or Quintype search API, a
Guardian-style day page). A pattern works when the two days give mostly different article
links on the outlet's own site: a page that ignores the date (redirecting to the front page,
say) gives the same links for both days and is rejected.

Only a few pages per outlet are read, politely (robots.txt, a pause between requests). The
result is a short report to paste back; nothing is collected.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from urllib.parse import urljoin, urlsplit

from carcux_data.j24.fetch import Disallowed, Fetcher

DAYS = (date(2024, 7, 20), date(2024, 7, 25))
MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()

# {d}: 2024-07-20, {y} {m} {dd}: 2024 07 20, {mon}: jul, {ms0} {ms1}: day start/end, epoch ms
PATTERNS = [
    ("archive-date", "/archive/{d}"),
    ("archive-ymd", "/archive/{y}/{m}/{dd}"),
    ("archive-query", "/archive?date={d}"),
    ("archive-php", "/archive.php?date={d}"),
    ("ymd-path", "/{y}/{m}/{dd}"),
    ("wordpress-api", "/wp-json/wp/v2/posts?after={d}T00:00:00&before={d}T23:59:59&per_page=100"
                      "&_fields=link,date,title"),
    ("quintype-api", "/api/v1/advanced-search?published-after={ms0}&published-before={ms1}"
                     "&limit=100&fields=url,headline,published-at"),
    ("guardian-day", "/world/bangladesh/{y}/{mon}/{dd}/all"),
]  # fmt: skip

_HREF = re.compile(r"""href\s*=\s*["']([^"'#]+)["']""", re.I)
_URLISH = re.compile(r'"(?:url|link)"\s*:\s*"(https?:[^"]+)"')


def fill(template: str, d: date) -> str:
    start = datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp() * 1000
    return template.format(d=d.isoformat(), y=d.year, m=f"{d.month:02d}", dd=f"{d.day:02d}",
                           mon=MONTHS[d.month - 1], ms0=int(start) - 6 * 3600_000,
                           ms1=int(start) + 18 * 3600_000)  # fmt: skip


def article_links(body: str, base: str, host: str) -> set[str]:
    """Links on the outlet's own site that look like articles (a long slug or a number)."""
    found = set(_URLISH.findall(body.replace("\\/", "/"))) | {
        urljoin(base, h) for h in _HREF.findall(body)
    }  # fmt: skip
    out = set()
    for u in found:
        p = urlsplit(u)
        if (p.hostname or "").removeprefix("www.") != host.removeprefix("www."):
            continue
        path = p.path.rstrip("/")
        last = path.rsplit("/", 1)[-1]
        if re.search(r"\d{4,}", last) or (last.count("-") >= 3 and len(last) > 20):
            out.add(f"{p.scheme}://{p.netloc}{path}")
    return out


@dataclass
class Probe:
    key: str
    host: str
    works: list[tuple[str, int, int]] = field(default_factory=list)  # (pattern, day1, day2)
    notes: list[str] = field(default_factory=list)
    front: str = ""  # what the front page gave: "200, 85 links", "403", …


def _front(fetcher: Fetcher, host: str) -> str:
    """The front page's status and article links: tells blocking apart from a missing page."""
    try:
        status, body, final = fetcher.get_page(f"https://{host}/")
    except Disallowed:
        return "robots"
    except OSError as exc:
        return type(exc).__name__
    if status >= 400:
        return str(status)
    n = len(article_links(body.decode("utf-8", "replace"), final, host))
    return f"{status}, {n} links"


def probe_outlet(fetcher: Fetcher, key: str, host: str, *,
                 log: Callable[[str], None] = print) -> Probe:  # fmt: skip
    result = Probe(key, host, front=_front(fetcher, host))
    for name, template in PATTERNS:
        sets = []
        for d in DAYS:
            url = f"https://{host}{fill(template, d)}"
            try:
                status, body, final = fetcher.get_page(url)
            except Disallowed:
                sets = None
                result.notes.append(f"{name}: robots.txt disallows")
                break
            except OSError as exc:
                sets = None
                result.notes.append(f"{name}: not reachable ({type(exc).__name__})")
                break
            if status >= 400:
                sets = None
                result.notes.append(f"{name} {status}")
                break
            text = body.decode("utf-8", "replace")
            if name.endswith("-api"):
                try:
                    json.loads(text)
                except ValueError:
                    sets = None
                    result.notes.append(f"{name} not-json")
                    break
            sets.append(article_links(text, final or url, host))
        if not sets or len(sets) < 2:
            continue
        a, b = sets
        if not (len(a) >= 5 and len(b) >= 5 and len(a & b) <= 0.3 * min(len(a), len(b))):
            result.notes.append(f"{name} 200 {len(a)}/{len(b)} links, {len(a & b)} same")
        if len(a) >= 5 and len(b) >= 5 and len(a & b) <= 0.3 * min(len(a), len(b)):
            result.works.append((name, len(a), len(b)))
            log(f"[{key}] {name} works ({len(a)} and {len(b)} links on two days)")
            if len(a) >= 40:
                break  # good enough; save the outlet the remaining requests
    return result


def report(results: list[Probe]) -> str:
    lines = ["CARCUX-J24 archive probe (paste this back)", ""]
    for r in sorted(results, key=lambda r: r.key):
        if r.works:
            best = ", ".join(f"{n} {a}/{b}" for n, a, b in r.works)
            lines.append(f"{r.key:16} {r.host:28} OK   {best} (front {r.front})")
        else:
            lines.append(f"{r.key:16} {r.host:28} NONE front {r.front}; "
                         f"{'; '.join(r.notes)[:300]}")  # fmt: skip
    ok = sum(1 for r in results if r.works)
    lines += ["", f"{ok} of {len(results)} outlets have a working date listing."]
    return "\n".join(lines)
