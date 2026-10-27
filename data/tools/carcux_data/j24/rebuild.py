"""Re-read every collected article from the local cache with the current reader, and join
the article files of parallel runs into one.

Collection ran in several folders at once (the main folder and part folders sharing one
cache), and the first reader missed the text of pages laid out without paragraphs. This
reads each saved page again, offline: nothing is fetched, and an article whose page is
not in the cache keeps its first record. Duplicates (an article read by two runs) are
dropped. Output: news/articles_all.jsonl; the per-run files are left as they were.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from carcux_data.j24 import WINDOW
from carcux_data.j24.fetch import Disallowed, Fetcher, Response
from carcux_data.j24.news import MIN_TEXT, WAYBACK, day_key, load_urls, read_article


def _offline(url: str, headers: dict) -> Response:
    raise OSError("offline: page not in the cache")


@dataclass
class OutletStats:
    records: int = 0
    reread: int = 0
    with_text_before: int = 0
    with_text: int = 0
    about_before: int = 0
    about: int = 0
    in_window: int = 0
    sources: Counter = field(default_factory=Counter)


def _in_window(published: str | None) -> bool | None:
    if not published or len(published) < 10:
        return None
    return WINDOW[0] <= published[:10] <= WINDOW[1]


def rebuild(out: Path, parts: list[Path], *, log: Callable[[str], None] = print
            ) -> dict[str, OutletStats]:  # fmt: skip
    urls = {u["url"]: u for u in load_urls(out)}
    fetcher = Fetcher(out / "cache", opener=_offline, sleep=lambda s: None, log=lambda m: None)
    files = [out / "news" / "articles.jsonl"] + [p / "news" / "articles.jsonl" for p in parts]
    seen: set[str] = set()
    stats: dict[str, OutletStats] = {}
    target = out / "news" / "articles_all.jsonl"
    tmp = target.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for path in files:
            if not path.exists():
                log(f"  {path} not found; skipped")
                continue
            for n, line in enumerate(path.read_text("utf-8").splitlines(), start=1):
                try:
                    r = json.loads(line)
                except ValueError:
                    continue  # a line cut off by a crash
                if r.get("url") in seen:
                    continue
                seen.add(r["url"])
                s = stats.setdefault(r["outlet"], OutletStats())
                s.records += 1
                s.with_text_before += r.get("text_chars", 0) >= MIN_TEXT
                s.about_before += bool(r.get("about_uprising"))
                u = urls.get(r["url"])
                when = (u.get("capture") or day_key(u)) if u else None
                if r.get("text_from", "wayback") == "wayback" and when:
                    try:
                        status, body, _ = fetcher.get_page(f"{WAYBACK}/{when}id_/{r['url']}")
                    except (OSError, Disallowed):
                        status, body = 0, b""
                    if status and status < 400 and body:
                        art = read_article(body)
                        art["title"] = art["title"] or r.get("title") or ""
                        art["published_at"] = art["published_at"] or r.get("published_at")
                        r.update(art)
                        s.reread += 1
                r["published_in_window"] = _in_window(r.get("published_at"))
                s.with_text += r.get("text_chars", 0) >= MIN_TEXT
                s.about += bool(r.get("about_uprising"))
                s.in_window += r["published_in_window"] is True
                s.sources[r.get("text_source", "paragraphs")] += 1
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                if n % 5000 == 0:
                    log(f"  {path.parent.parent.name}: {n} records done")
    tmp.replace(target)
    return stats


def report(stats: dict[str, OutletStats]) -> str:
    head = (f"{'outlet':16}{'articles':>9}{'re-read':>9}{'text before':>12}{'text now':>10}"
            f"{'about before':>13}{'about now':>11}{'in window':>10}")  # fmt: skip
    lines = [head]
    names = ("records", "reread", "with_text_before", "with_text", "about_before", "about",
             "in_window")  # fmt: skip
    widths = (9, 9, 12, 10, 13, 11, 10)
    tot = OutletStats()

    def row(label: str, s: OutletStats) -> str:
        return f"{label:16}" + "".join(
            f"{getattr(s, n):>{w}}" for n, w in zip(names, widths, strict=True)
        )

    for key, s in sorted(stats.items(), key=lambda kv: -kv[1].records):
        lines.append(row(key, s))
        for name in names:
            setattr(tot, name, getattr(tot, name) + getattr(s, name))
    lines.append(row("TOTAL", tot))
    lines.append(f"\n'text' = at least {MIN_TEXT} characters of article text; 'in window' = "
                 f"published {WINDOW[0]} to {WINDOW[1]}.")  # fmt: skip
    return "\n".join(lines)
