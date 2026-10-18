"""Command line for the CARCUX-J24 pilot.

    python -m carcux_data.j24 index --out DIR [--sites a,b] [--contact EMAIL]
    python -m carcux_data.j24 recurrence --out DIR
    python -m carcux_data.j24 claim-sheet --out DIR
    python -m carcux_data.j24 check-sheet FILE
    python -m carcux_data.j24 news-list --out DIR [--outlets a,b] [--since D --until D]
    python -m carcux_data.j24 news-fetch --out DIR [--outlets a,b] [--since D --until D]
                                         [--limit N] [--text-from wayback|live]

`index` needs CARCUX_J24_SALT: a long random secret that turns social-media links into
salted hashes in the public files. Make one, keep it private, never paste it in chat:

    python -c "import secrets; print(secrets.token_hex(32))"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from carcux_data.j24 import WINDOW
from carcux_data.j24.fetch import Fetcher
from carcux_data.j24.sites import SITES, by_key


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m carcux_data.j24", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="command", required=True)
    ix = sub.add_parser("index", help="index the fact-checks in the window")
    ix.add_argument("--out", required=True, type=Path)
    ix.add_argument("--sites", default=",".join(s.key for s in SITES))
    ix.add_argument("--since", default=WINDOW[0])
    ix.add_argument("--until", default=WINDOW[1])
    ix.add_argument("--contact", help="an e-mail for the User-Agent, so sites can reach you")
    ix.add_argument("--delay", type=float, default=2.0, help="seconds between requests")
    rc = sub.add_parser("recurrence", help="go / no-go numbers from factchecks.jsonl")
    rc.add_argument("--out", required=True, type=Path)
    rc.add_argument("--all", action="store_true", help="count every fact-check, not only "
                    "those likely about the uprising")  # fmt: skip
    cs = sub.add_parser("claim-sheet", help="the Excel sheet for restating claims")
    cs.add_argument("--out", required=True, type=Path)
    ck = sub.add_parser("check-sheet", help="check a filled claim sheet")
    ck.add_argument("file", type=Path)
    for name, help_ in (("news-list", "list the outlets' articles captured in the window"),
                        ("news-fetch", "read the listed articles")):  # fmt: skip
        n = sub.add_parser(name, help=help_)
        n.add_argument("--out", required=True, type=Path)
        n.add_argument("--outlets", default="", help="keys from news_outlets.csv; default all")
        n.add_argument("--since", default=WINDOW[0])
        n.add_argument("--until", default=WINDOW[1])
        n.add_argument("--delay", type=float, default=4.0, help="seconds between requests")
        n.add_argument("--contact", help="an e-mail for the User-Agent")
        if name == "news-list":
            n.add_argument(
                "--from",
                dest="list_from",
                choices=["sitemaps", "archive"],
                default="sitemaps",
                help="the outlets' sitemaps (fast), or the Internet Archive's index (slow; "
                "for outlets without sitemaps)",
            )
            n.add_argument("--parallel", type=int, default=6, help="outlets listed at once")
        if name == "news-fetch":
            n.add_argument("--limit", type=int, help="at most this many articles per outlet")
            n.add_argument("--text-from", choices=["wayback", "live"], default="wayback")
            n.add_argument("--only-likely", action="store_true", help="skip articles whose "
                           "listed title does not name the uprising")  # fmt: skip
    args = ap.parse_args(argv)

    if args.command == "index":
        from carcux_data.j24.index import run

        salt = os.environ.get("CARCUX_J24_SALT", "")
        if len(salt) < 32:
            print("Set CARCUX_J24_SALT to a private random value of at least 32 characters "
                  "first (see --help).", file=sys.stderr)  # fmt: skip
            return 2
        sites = [by_key(k.strip()) for k in args.sites.split(",") if k.strip()]
        fetcher = Fetcher(args.out / "cache", delay=args.delay, contact=args.contact)
        result = run(args.out, sites, salt, since=args.since, until=args.until, fetcher=fetcher)
        print(f"\n{result.posts} fact-checks written to {args.out / 'factchecks.jsonl'} "
              f"({fetcher.requests} requests).")  # fmt: skip
        return 0 if result.posts else 1

    if args.command == "recurrence":
        from carcux_data.j24.recurrence import load, report, summarise

        summary = summarise(load(args.out / "factchecks.jsonl"), in_scope_only=not args.all)
        text = report(summary)
        (args.out / "recurrence.txt").write_text(text, encoding="utf-8")
        (args.out / "recurrence.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(text)
        return 0

    if args.command == "claim-sheet":
        from carcux_data.j24.recurrence import load
        from carcux_data.j24.sheet import write_sheet

        path = args.out / "claim_sheet.xlsx"
        if path.exists():
            print(f"{path} exists: it may hold your work. Rename it first.", file=sys.stderr)
            return 2
        n = write_sheet(load(args.out / "factchecks.jsonl"), path)
        print(f"{n} rows written to {path}")
        return 0

    if args.command in ("news-list", "news-fetch"):
        return _news(args)

    from carcux_data.j24.sheet import check_sheet

    problems = check_sheet(args.file)
    print("\n".join(problems) if problems else "The sheet is complete.")
    return 1 if problems else 0


def _news(args) -> int:
    from carcux_data.j24 import news

    outlets = news.load_news_outlets()
    keys = [k.strip() for k in args.outlets.split(",") if k.strip()] or list(outlets)
    unknown = [k for k in keys if k not in outlets]
    if unknown:
        print(f"Unknown outlets: {', '.join(unknown)}. Known: {', '.join(outlets)}",
              file=sys.stderr)  # fmt: skip
        return 2
    if args.command == "news-list":
        return _news_list(args, outlets, keys)
    fetcher = Fetcher(args.out / "cache", delay=args.delay, contact=args.contact)
    if not news.load_urls(args.out):
        print("No article list yet: run news-list first.", file=sys.stderr)
        return 2
    results = news.fetch_articles(
        fetcher, args.out, outlets, keys=keys, since=args.since, until=args.until,
        limit=args.limit, text_from=args.text_from, only_likely=args.only_likely,
    )  # fmt: skip
    for r in results:
        extra = [f"{r.failed} failed"]
        if r.not_archived:
            extra.append(f"{r.not_archived} not in the archive")
        if r.late:
            extra.append(f"{r.late} from copies captured long after the window")
        if r.skipped:
            extra.append(f"{r.skipped} skipped (title not about the uprising)")
        problem = f" — {r.problem}" if r.problem else ""
        print(f"{r.outlet}: {r.fetched} of {r.listed} read, {r.about_uprising} about the "
              f"uprising, {', '.join(extra)}{problem}")  # fmt: skip
    print(f"\n{fetcher.requests} requests. Articles in {args.out / 'news' / 'articles.jsonl'}.")
    return 0


def _news_list(args, outlets, keys) -> int:
    import re
    from collections import Counter
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from datetime import date

    from carcux_data.j24 import news
    from carcux_data.j24.sitemaps import list_from_sitemaps

    def one(key):
        o = outlets[key]

        def say(message: str) -> None:
            print(f"[{key}] {message.strip()}", flush=True)

        delay = args.delay if args.list_from == "archive" else min(args.delay, 2.0)
        fetcher = Fetcher(args.out / "cache", delay=delay, contact=args.contact, log=say)
        if args.list_from == "archive":
            first = news.list_outlet(fetcher, o, args.since, args.until, log=say)
            days = Counter(news.capture_day(ts) for ts in first.values())
            return key, first, len(first), days, None
        hosts = sorted({p.split("/", 1)[0].removeprefix("www.") for p in o.prefixes})
        pattern = re.compile(o.url_regex, re.I) if o.url_regex else None

        def keep(url, title):
            return pattern is None or bool(pattern.search(f"{url} {title or ''}"))

        span = date.fromisoformat(args.since), date.fromisoformat(args.until)
        got = list_from_sitemaps(fetcher, hosts, *span, keep=keep, log=say)
        days = Counter((r["published"] or "")[:10] for r in got.rows)
        note = (f"{got.sitemaps_read} sitemaps read"
                + (f", {got.sitemaps_skipped} left unread" if got.sitemaps_skipped else "")
                + (f", {got.undated} undated left out" if got.undated else "")
                + (f" — {got.problem}" if got.problem else ""))  # fmt: skip
        return key, got.rows, len(got.rows), days, note

    total = 0
    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        for done in as_completed([pool.submit(one, k) for k in keys]):
            key, found, n, days, note = done.result()
            news.write_urls(args.out, outlets[key], found,
                            "archive" if args.list_from == "archive" else "sitemap")  # fmt: skip
            first_days = ", ".join(f"{d} {c}" for d, c in sorted(days.items())[:3])
            hint = "" if n else "  <- none: try --from archive for this outlet"
            print(f"{key}: {n} articles in the window"
                  + (f" (first days: {first_days} …)" if n else "")
                  + (f"; {note}" if note else "") + hint)  # fmt: skip
            total += n
    print(f"\n{total} article addresses listed in {args.out / 'news' / 'urls.jsonl'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
