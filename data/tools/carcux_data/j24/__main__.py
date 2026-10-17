"""Command line for the CARCUX-J24 pilot.

    python -m carcux_data.j24 index --out DIR [--sites a,b] [--contact EMAIL]
    python -m carcux_data.j24 recurrence --out DIR
    python -m carcux_data.j24 claim-sheet --out DIR
    python -m carcux_data.j24 check-sheet FILE

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

    from carcux_data.j24.sheet import check_sheet

    problems = check_sheet(args.file)
    print("\n".join(problems) if problems else "The sheet is complete.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
