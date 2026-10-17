"""Index the fact-checks published in the study window, site by site.

Output (in the folder given with --out, never inside the repository):

    factchecks.jsonl               one record per fact-check: link, dates, title, verdict
                                   words, scope hint, cited outlets and link counts
    restricted/social_links.jsonl  links to social media posts, by fact-check (may lead
                                   to private individuals: not for publication)
    cache/                         every API response, so a re-run sends no requests
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode

from carcux_data.j24 import WINDOW
from carcux_data.j24.extract import (
    account_of,
    account_ref,
    classify,
    clean_title,
    load_outlets,
    read_html,
    scope_terms,
    url_ref,
    verdict_words,
)
from carcux_data.j24.fetch import Disallowed, Fetcher
from carcux_data.j24.sites import Site

PER_PAGE = 50
MAX_PAGES = 200  # a safety stop: the window holds a few hundred posts per site


@dataclass
class SiteResult:
    site: str
    posts: int = 0
    in_scope_hint: int = 0
    problem: str | None = None
    pages: int = 0


@dataclass
class IndexResult:
    sites: list[SiteResult] = field(default_factory=list)

    @property
    def posts(self) -> int:
        return sum(s.posts for s in self.sites)


def _categories(fetcher: Fetcher, site: Site, ids: set[int]) -> dict[int, str]:
    names: dict[int, str] = {}
    pending = sorted(ids)
    while pending:
        chunk, pending = pending[:100], pending[100:]
        query = urlencode({"include": ",".join(map(str, chunk)), "per_page": 100,
                           "_fields": "id,name"})  # fmt: skip
        status, _, data = fetcher.get_json(f"{site.api}/categories?{query}")
        if status == 200 and isinstance(data, list):
            names.update({c["id"]: c["name"] for c in data if "id" in c and "name" in c})
    return names


def record_for(post: dict, site: Site, categories: dict[int, str], outlets, salt: str):
    """(public record, restricted social links) for one WordPress post."""
    title = clean_title(post.get("title", {}).get("rendered", ""))
    links, text = read_html(post.get("content", {}).get("rendered", ""))
    cats = [categories.get(c, str(c)) for c in post.get("categories", [])]
    verdict, words = verdict_words(title, text, cats)
    terms = scope_terms(title, text)
    cited: Counter = Counter()
    info: dict[tuple[str, str], dict] = {}
    social = []
    for href in dict.fromkeys(links):  # each distinct link once
        link = classify(href, outlets, site.domains)
        if link is None or link.kind == "fact_checker":
            continue
        if link.kind == "social":
            account = account_of(href, link.platform)
            social.append({
                "platform": link.platform, "url": href, "url_ref": url_ref(salt, href),
                "account_ref": account_ref(salt, link.platform, account) if account else None,
            })  # fmt: skip
            continue
        key = (link.kind, link.domain)
        cited[key] += 1
        info[key] = {
            "kind": link.kind,
            "domain": link.domain,
            "outlet": link.outlet.name if link.outlet else None,
            "country": link.outlet.country if link.outlet else None,
        }
    fid = f"{site.key}:{post['id']}"
    public = {
        "factcheck_id": fid,
        "site": site.key,
        "fact_checker": site.name,
        "language": site.language,
        "url": post.get("link"),
        "published_at": post.get("date_gmt") or post.get("date"),
        "modified_at": post.get("modified_gmt") or post.get("modified"),
        "title": title,
        "categories": cats,
        "verdict_hint": verdict,
        "verdict_words": words,
        "scope_hint": bool(terms),
        "scope_terms": terms,
        "cited": [{**info[k], "links": n} for k, n in sorted(cited.items())],
        "social_links": [
            {"platform": s["platform"], "url_ref": s["url_ref"], "account_ref": s["account_ref"]}
            for s in social
        ],
    }
    restricted = [{"factcheck_id": fid, **s} for s in social]
    return public, restricted


def index_site(
    fetcher: Fetcher, site: Site, since: str, until: str, outlets, salt: str, write
) -> SiteResult:
    result = SiteResult(site.key)
    posts: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        query = urlencode({
            "after": f"{since}T00:00:00", "before": f"{until}T23:59:59", "per_page": PER_PAGE,
            "page": page, "orderby": "date", "order": "asc",
            "_fields": "id,date,date_gmt,modified,modified_gmt,link,title,content,categories",
        })  # fmt: skip
        try:
            status, headers, data = fetcher.get_json(f"{site.api}/posts?{query}")
        except Disallowed:
            result.problem = "robots.txt disallows the API; index this site by hand"
            return result
        except OSError as exc:
            result.problem = f"not reachable ({exc}); try again later"
            return result
        if status == 400 and page > 1:  # WordPress: page past the end
            break
        if status != 200 or not isinstance(data, list):
            result.problem = (
                f"did not answer as WordPress (HTTP {status}); index by hand or add an adapter"
            )
            return result
        result.pages = page
        posts.extend(data)
        total_pages = int(headers.get("x-wp-totalpages", page))
        if page >= total_pages or len(data) < PER_PAGE:
            break
    categories = _categories(fetcher, site, {c for p in posts for c in p.get("categories", [])})
    for post in posts:
        public, restricted = record_for(post, site, categories, outlets, salt)
        write(public, restricted)
        result.posts += 1
        result.in_scope_hint += public["scope_hint"]
    return result


def run(
    out: Path,
    sites: list[Site],
    salt: str,
    *,
    since: str = WINDOW[0],
    until: str = WINDOW[1],
    fetcher: Fetcher | None = None,
    log: Callable[[str], None] = print,
) -> IndexResult:
    out = Path(out)
    (out / "restricted").mkdir(parents=True, exist_ok=True)
    fetcher = fetcher or Fetcher(out / "cache", log=log)
    outlets = load_outlets()
    result = IndexResult()
    seen: set[str] = set()
    public_path = out / "factchecks.jsonl"
    restricted_path = out / "restricted" / "social_links.jsonl"
    with (
        public_path.open("w", encoding="utf-8") as pub,
        restricted_path.open("w", encoding="utf-8") as res,
    ):

        def write(public: dict, restricted: list[dict]) -> None:
            if public["factcheck_id"] in seen:
                return
            seen.add(public["factcheck_id"])
            pub.write(json.dumps(public, ensure_ascii=False) + "\n")
            for r in restricted:
                res.write(json.dumps(r, ensure_ascii=False) + "\n")

        for site in sites:
            log(f"{site.key}: indexing {since} to {until} …")
            r = index_site(fetcher, site, since, until, outlets, salt, write)
            log(f"{site.key}: {r.posts} fact-checks, {r.in_scope_hint} likely about the uprising"
                + (f" — {r.problem}" if r.problem else ""))  # fmt: skip
            result.sites.append(r)
    return result
