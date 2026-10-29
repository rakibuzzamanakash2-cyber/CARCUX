"""Command line for the CARCUX-J24 pilot.

    python -m carcux_data.j24 index --out DIR [--sites a,b] [--contact EMAIL]
    python -m carcux_data.j24 recurrence --out DIR
    python -m carcux_data.j24 claim-sheet --out DIR
    python -m carcux_data.j24 check-sheet FILE
    python -m carcux_data.j24 split-sheet --out DIR [--size 25] [--only-likely] [--checked-by P]
    python -m carcux_data.j24 merge-sheets --out DIR
    python -m carcux_data.j24 news-list --out DIR [--outlets a,b] [--since D --until D]
    python -m carcux_data.j24 news-probe --out DIR [--outlets a,b]
    python -m carcux_data.j24 factcheck-export --out DIR [--batch 40]
    python -m carcux_data.j24 news-rebuild --out DIR [--parts part2,part4]
    python -m carcux_data.j24 news-texts --out DIR
    python -m carcux_data.j24 claims-match --out DIR --claims FILE [--top 10] [--embed]
    python -m carcux_data.j24 stance-auto --out DIR [--claims-bn FILE]
    python -m carcux_data.j24 stance-eval --out DIR --key FILE --sheets A.xlsx,B.xlsx,C.xlsx
    python -m carcux_data.j24 fuse --out DIR --claims FILE [--stances auto|human]
                                   [--key FILE --sheets A,B,C]
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
    sp = sub.add_parser("split-sheet", help="split claim_sheet.xlsx into small batches")
    sp.add_argument("--out", required=True, type=Path)
    sp.add_argument("--size", type=int, default=25, help="fact-checks per batch")
    sp.add_argument("--only-likely", action="store_true", help="only rows likely in scope")
    sp.add_argument("--checked-by", default="", help="the helper's pseudonym, never a name")
    mg = sub.add_parser("merge-sheets", help="join the batches into claim_sheet_merged.xlsx")
    mg.add_argument("--out", required=True, type=Path)
    sm = sub.add_parser("news-sample", help="copy a few saved pages per outlet to samples/")
    sm.add_argument("--out", required=True, type=Path)
    sm.add_argument("--outlets", required=True)
    sm.add_argument("--n", type=int, default=3)
    fx = sub.add_parser("factcheck-export", help="fact-check texts from the cache, in batches")
    fx.add_argument("--out", required=True, type=Path)
    fx.add_argument("--batch", type=int, default=40)
    rb = sub.add_parser("news-rebuild", help="re-read collected articles offline and join "
                        "the runs into news/articles_all.jsonl")  # fmt: skip
    rb.add_argument("--out", required=True, type=Path)
    rb.add_argument("--parts", default="", help="part folders inside --out, e.g. part2,part4")
    nt = sub.add_parser("news-texts", help="article texts from the saved pages, for matching")
    nt.add_argument("--out", required=True, type=Path)
    cm = sub.add_parser("claims-match", help="candidate articles for each claim group")
    cm.add_argument("--out", required=True, type=Path)
    cm.add_argument("--claims", required=True, type=Path, help="claims v1 .jsonl")
    cm.add_argument("--top", type=int, default=10)
    cm.add_argument("--embed", action="store_true", help="add the multilingual sentence model")
    cm.add_argument(
        "--force",
        action="store_true",
        help="overwrite existing candidates (they may already be in labelling)",
    )
    sa = sub.add_parser("stance-auto", help="features for the automatic stance baseline")
    sa.add_argument("--out", required=True, type=Path)
    sa.add_argument("--claims-bn", type=Path, help="Bangla claims, one JSON line per group")
    se = sub.add_parser("stance-eval", help="agreement and baseline scores from the sheets")
    se.add_argument("--out", required=True, type=Path)
    se.add_argument("--key", required=True, type=Path)
    se.add_argument("--sheets", required=True, help="the returned part sheets, comma-separated")
    fu = sub.add_parser("fuse", help="claim truth from the outlets' stances (Paper 1)")
    fu.add_argument("--out", required=True, type=Path)
    fu.add_argument("--claims", required=True, type=Path)
    fu.add_argument("--stances", choices=["auto", "human"], default="auto")
    fu.add_argument("--key", type=Path)
    fu.add_argument("--sheets", default="")
    pr = sub.add_parser("news-probe", help="find each outlet's date-listing pages")
    pr.add_argument("--out", required=True, type=Path)
    pr.add_argument("--outlets", default="", help="keys from news_outlets.csv; default all")
    pr.add_argument("--parallel", type=int, default=8)
    pr.add_argument("--contact", help="an e-mail for the User-Agent")
    pr.add_argument(
        "--gdelt-day",
        default="2024-08-02",
        help="one day for which GDELT's article lists are read and compared",
    )
    pr.add_argument("--skip-pages", action="store_true", help="only the GDELT check")
    pr.add_argument("--skip-gdelt", action="store_true", help="only the date pages")
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
                choices=["sitemaps", "archive", "archive-pages"],
                default="sitemaps",
                help="the outlets' sitemaps (fast), or the Internet Archive's index for "
                "outlets without sitemaps: archive-pages reads it page by page (recommended), "
                "archive week by week (often times out)",
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

    if args.command in ("split-sheet", "merge-sheets"):
        return _batches(args)

    if args.command == "news-sample":
        from carcux_data.j24.sample import sample

        keys = [k.strip() for k in args.outlets.split(",") if k.strip()]
        files = sample(args.out, keys, n=args.n)
        print(f"{len(files)} pages copied to {args.out / 'samples'}")
        return 0 if files else 1

    if args.command == "factcheck-export":
        from carcux_data.j24.export import export

        files = export(args.out, batch=args.batch)
        rows = sum(len(p.read_text("utf-8").splitlines()) for p in files)
        print(f"{rows} fact-checks in {len(files)} files in {args.out / 'factcheck_export'}")
        return 0 if rows else 1

    if args.command == "news-rebuild":
        from carcux_data.j24.rebuild import rebuild, report

        parts = [args.out / p.strip() for p in args.parts.split(",") if p.strip()]
        text = report(rebuild(args.out, parts, log=lambda m: print(m, flush=True)))
        (args.out / "news" / "rebuild.txt").write_text(text, encoding="utf-8")
        print("\n" + text)
        return 0

    if args.command == "news-texts":
        from carcux_data.j24.match import news_texts

        n = news_texts(args.out, log=lambda m: print(m, flush=True))
        print(f"{n} article texts in {args.out / 'news' / 'texts.jsonl'}")
        return 0 if n else 1

    if args.command == "claims-match":
        from collections import Counter

        from carcux_data.j24.match import match

        if (args.out / "matches" / "candidates.jsonl").exists() and not args.force:
            print(
                "matches/candidates.jsonl exists and may already be in labelling; the "
                "pair numbers would change. Use --force to overwrite it anyway."
            )
            return 1
        res = match(args.out, args.claims, top=args.top, embed=args.embed,
                    log=lambda m: print(m, flush=True))  # fmt: skip
        groups = Counter(r["claim_group"] for r in res)
        print(f"{len(res)} candidate pairs for {len(groups)} claim groups in "
              f"{args.out / 'matches'}")  # fmt: skip
        return 0 if res else 1

    if args.command == "stance-auto":
        from carcux_data.j24.stance import score

        rows = score(args.out, args.claims_bn, log=lambda m: print(m, flush=True))
        print(f"{len(rows)} pairs scored in {args.out / 'matches' / 'stance_features.jsonl'}")
        return 0 if rows else 1

    if args.command == "stance-eval":
        from carcux_data.j24.stance import evaluate

        sheets = [Path(p.strip()) for p in args.sheets.split(",") if p.strip()]
        print(json.dumps(evaluate(args.out, sheets, args.key), indent=1))
        return 0

    if args.command == "fuse":
        from carcux_data.j24.fusion import run

        sheets = [Path(p.strip()) for p in args.sheets.split(",") if p.strip()]
        rep = run(args.out, args.claims, stances=args.stances, sheets=sheets, key=args.key,
                  log=lambda m: print(m, flush=True))  # fmt: skip
        print(json.dumps(rep, indent=1))
        return 0

    if args.command == "news-probe":
        return _probe(args)

    if args.command in ("news-list", "news-fetch"):
        return _news(args)

    from carcux_data.j24.sheet import check_sheet

    problems = check_sheet(args.file)
    print("\n".join(problems) if problems else "The sheet is complete.")
    return 1 if problems else 0


def _batches(args) -> int:
    from carcux_data.j24.batches import merge_sheets, split_sheet
    from carcux_data.j24.sheet import check_sheet

    folder = args.out / "batches"
    if args.command == "split-sheet":
        source = args.out / "claim_sheet.xlsx"
        if not source.exists():
            print(f"{source} not found: run claim-sheet first.", file=sys.stderr)
            return 2
        if folder.exists() and any(folder.glob("batch_*.xlsx")):
            print(f"{folder} already holds batches, which may hold work. Merge them first, "
                  "then move the folder away.", file=sys.stderr)  # fmt: skip
            return 2
        written = split_sheet(source, folder, size=args.size, only_likely=args.only_likely,
                              checked_by=args.checked_by)  # fmt: skip
        for path, n, hinted in written:
            print(f"{path.name}: {n} fact-checks, {hinted} with a maybe-same hint")
        print(f"\n{len(written)} batches in {folder}. Send one at a time.")
        return 0
    files = sorted(folder.glob("batch_*.xlsx"))
    if not files:
        print(f"No batches in {folder}.", file=sys.stderr)
        return 2
    out = args.out / "claim_sheet_merged.xlsx"
    if out.exists():
        print(f"{out} exists: rename it first.", file=sys.stderr)
        return 2
    try:
        n = merge_sheets(files, out)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    problems = check_sheet(out)
    print(f"{n} rows from {len(files)} batches written to {out}")
    print("\n".join(problems) if problems else "The merged sheet is complete.")
    return 1 if problems else 0


def _probe(args) -> int:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from carcux_data.j24 import news
    from carcux_data.j24.probe import probe_outlet, report

    outlets = news.load_news_outlets()
    keys = [k.strip() for k in args.outlets.split(",") if k.strip()] or list(outlets)
    unknown = [k for k in keys if k not in outlets]
    if unknown:
        print(f"Unknown outlets: {', '.join(unknown)}", file=sys.stderr)
        return 2
    jobs = [(k, h) for k in keys
            for h in sorted({p.split("/", 1)[0] for p in outlets[k].prefixes})]  # fmt: skip

    def one(job):
        key, host = job
        f = Fetcher(args.out / "cache", delay=2.0, contact=args.contact,
                    log=lambda m: print(f"[{key}] {m.strip()}", flush=True))  # fmt: skip
        return probe_outlet(f, key, host, log=lambda m: print(m, flush=True))

    results = []
    text = ""
    if not args.skip_pages:
        with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
            for done in as_completed([pool.submit(one, j) for j in jobs]):
                results.append(done.result())
        text = report(results)
    if not args.skip_gdelt:
        text += ("\n\n" if text else "") + _gdelt_check(args, outlets, keys)
    (args.out / "news").mkdir(parents=True, exist_ok=True)
    (args.out / "news" / "probe.txt").write_text(text, encoding="utf-8")
    print("\n" + text)
    return 0


def _gdelt_check(args, outlets, keys) -> str:
    from datetime import date

    from carcux_data.j24 import gdelt, news

    day = date.fromisoformat(args.gdelt_day)
    hosts = {p.split("/", 1)[0].removeprefix("www."): k for k in keys for p in outlets[k].prefixes}
    print(f"\nReading GDELT's article lists for {day} (192 small files, a few minutes)…",
          flush=True)  # fmt: skip
    f = Fetcher(args.out / "cache", delay=1.0, contact=args.contact,
                log=lambda m: print(f"[gdelt] {m.strip()}", flush=True))  # fmt: skip
    got = gdelt.sample_day(f, day, hosts, log=lambda m: print(m, flush=True))
    listed: dict[str, set[str]] = {}
    for row in news.load_urls(args.out):
        if row["outlet"] in keys and (news.day_key(row) or "")[:8] == f"{day:%Y%m%d}":
            if (u := news.normalise(row["url"])) is not None:
                listed.setdefault(row["outlet"], set()).add(u)
    lines = [
        f"GDELT check for {day}: {got.files_read} files read, {got.files_missing} missing"
        + (f" — {got.problem}" if got.problem else ""),
        "",
        f"{'outlet':16} {'GDELT':>6} {'our list':>8} {'both':>6}  GDELT has of our list",
    ]
    for k in sorted(keys):
        g = {u for a in got.by_outlet.get(k, ()) if (u := news.normalise(a))}
        ours = listed.get(k, set())
        share = f"{100 * len(g & ours) // len(ours)}%" if ours else "-"
        lines.append(f"{k:16} {len(g):>6} {len(ours):>8} {len(g & ours):>6}  {share}")
    return "\n".join(lines)


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

        from_archive = args.list_from in ("archive", "archive-pages")
        delay = args.delay if from_archive else min(args.delay, 2.0)
        fetcher = Fetcher(args.out / "cache", delay=delay, contact=args.contact, log=say)
        if from_archive:
            lister = (
                news.list_outlet_pages if args.list_from == "archive-pages" else news.list_outlet
            )
            first = lister(fetcher, o, args.since, args.until, log=say)
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
                            "sitemap" if args.list_from == "sitemaps" else "archive")  # fmt: skip
            first_days = ", ".join(f"{d} {c}" for d, c in sorted(days.items())[:3])
            hint = "" if n else "  <- none: try --from archive-pages for this outlet"
            print(f"{key}: {n} articles in the window"
                  + (f" (first days: {first_days} …)" if n else "")
                  + (f"; {note}" if note else "") + hint)  # fmt: skip
            total += n
    print(f"\n{total} article addresses listed in {args.out / 'news' / 'urls.jsonl'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
