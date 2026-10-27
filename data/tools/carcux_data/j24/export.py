"""Export the fact-check articles' text from the local cache, in small batches, so that
claim-sheet rows can be drafted from them and then checked by a person.

The index read each fact-checker's posts through its WordPress interface and kept the
answers in the cache; this reads them again offline (nothing is fetched). For each
fact-check it writes the title, the link, the date, the verdict words the indexer found,
and the article text, shortened to its opening and closing (where fact-checks state the
claim and the verdict). Social media links stay out: only text is exported.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode

from carcux_data.j24 import WINDOW
from carcux_data.j24.extract import clean_title, read_html
from carcux_data.j24.fetch import Fetcher, Response
from carcux_data.j24.index import MAX_PAGES, PER_PAGE
from carcux_data.j24.sites import SITES

HEAD, TAIL = 1500, 900  # characters kept from the start and the end of each article


def _offline(url: str, headers: dict) -> Response:
    raise OSError("offline: not in the cache")


def _posts(fetcher: Fetcher, site) -> list[dict]:
    posts: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        query = urlencode({
            "after": f"{WINDOW[0]}T00:00:00", "before": f"{WINDOW[1]}T23:59:59",
            "per_page": PER_PAGE, "page": page, "orderby": "date", "order": "asc",
            "_fields": "id,date,date_gmt,modified,modified_gmt,link,title,content,categories",
        })  # fmt: skip
        try:
            status, headers, data = fetcher.get_json(f"{site.api}/posts?{query}")
        except OSError:
            break
        if status != 200 or not isinstance(data, list):
            break
        posts.extend(data)
        if page >= int(headers.get("x-wp-totalpages", page)) or len(data) < PER_PAGE:
            break
    return posts


def shorten(text: str) -> str:
    if len(text) <= HEAD + TAIL + 50:
        return text
    return f"{text[:HEAD]} […] {text[-TAIL:]}"


def export(out: Path, batch: int = 40) -> list[Path]:
    hints = {}
    index = out / "factchecks.jsonl"
    if index.exists():
        for line in index.read_text("utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                hints[r["factcheck_id"]] = r
    fetcher = Fetcher(out / "cache", opener=_offline, sleep=lambda s: None, log=lambda m: None)
    rows = []
    for site in SITES:
        for post in _posts(fetcher, site):
            fid = f"{site.key}:{post['id']}"
            _, text = read_html(post.get("content", {}).get("rendered", ""))
            h = hints.get(fid, {})
            rows.append({
                "factcheck_id": fid, "fact_checker": site.name, "url": post.get("link"),
                "published_at": (post.get("date") or "")[:10],
                "title": clean_title(post.get("title", {}).get("rendered", "")),
                "verdict_hint": h.get("verdict_hint"), "scope_hint": h.get("scope_hint"),
                "text": shorten(text),
            })  # fmt: skip
    folder = out / "factcheck_export"
    folder.mkdir(exist_ok=True)
    for old in folder.glob("batch_*.jsonl"):
        old.unlink()
    written = []
    for i in range(0, len(rows), batch):
        path = folder / f"batch_{i // batch + 1:02d}.jsonl"
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                                for r in rows[i:i + batch]), encoding="utf-8")  # fmt: skip
        written.append(path)
    return written
