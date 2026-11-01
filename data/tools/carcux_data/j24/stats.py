"""The numbers and tables Paper 2 reports, from the files on disk (nothing is fetched).

Writes stats/summary.json and stats/tables.xlsx with one sheet per table:

- outlets: per outlet, its country and language, how many article addresses were listed,
  collected, had text, were published in the window, look like uprising stories, are in
  the matching corpus, and appear among the labelling candidates.
- days: articles published per day of the window, by language.
- claims: claims v1 by source, fact-checker, verdict, claim type and event type.
- candidates: the labelling pairs by outlet and language.
- coverage: per fact-checker, fact-checks published, in scope, and claim groups that have
  at least one candidate article.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from carcux_data.j24 import WINDOW
from carcux_data.j24.match import is_bangla
from carcux_data.j24.news import MIN_TEXT, load_news_outlets, load_urls


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    return rows


def compute(out: Path, claims_path: Path) -> dict:
    summary, tables = collect(out, claims_path)
    folder = out / "stats"
    folder.mkdir(exist_ok=True)
    (folder / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    _write_tables(folder / "tables.xlsx", tables)
    return summary


def collect(out: Path, claims_path: Path) -> tuple[dict, dict[str, list[dict]]]:
    """The summary numbers and the tables, without writing anything."""
    outlets = load_news_outlets()
    listed = Counter(u["outlet"] for u in load_urls(out))
    articles = _jsonl(out / "news" / "articles_all.jsonl")
    texts = _jsonl(out / "news" / "texts.jsonl")
    claims = _jsonl(claims_path)
    cands = _jsonl(out / "matches" / "candidates.jsonl")

    per = defaultdict(Counter)
    for k, n in listed.items():
        per[k]["listed"] = n
    for a in articles:
        p = per[a["outlet"]]
        p["collected"] += 1
        p["with_text"] += a.get("text_chars", 0) >= MIN_TEXT
        p["in_window"] += a.get("published_in_window") is True
        p["no_date"] += a.get("published_in_window") is None
        p["about_uprising"] += bool(a.get("about_uprising"))
    days = defaultdict(Counter)
    for t in texts:
        per[t["outlet"]]["corpus"] += 1
        d = (t.get("published_at") or "")[:10]
        if WINDOW[0] <= d <= WINDOW[1]:
            days[d]["bangla" if is_bangla(t) else "english"] += 1
    for c in cands:
        per[c["outlet"]]["candidates"] += 1

    outlet_rows = []
    for key in sorted(per, key=lambda k: -per[k]["collected"]):
        o = outlets.get(key)
        row = {"outlet": key, "name": o.name if o else key, "country": o.country if o else "",
               "language": o.language if o else ""}  # fmt: skip
        for col in ("listed", "collected", "with_text", "in_window", "no_date", "about_uprising",
                    "corpus", "candidates"):  # fmt: skip
            row[col] = per[key][col]
        outlet_rows.append(row)

    d0, d1 = date.fromisoformat(WINDOW[0]), date.fromisoformat(WINDOW[1])
    day_rows = []
    for i in range((d1 - d0).days + 1):
        d = (d0 + timedelta(days=i)).isoformat()
        day_rows.append({"day": d, "bangla": days[d]["bangla"], "english": days[d]["english"]})

    in_scope = [c for c in claims if c.get("in_scope") == "yes"]
    groups = {c.get("claim_group") or c["claim_id"] for c in in_scope}
    matched = {c["claim_group"] for c in cands}
    claim_rows = []
    for field in ("source", "fact_checker", "verdict", "claim_type", "event_type",
                  "evidence_tier", "ohchr_finding"):  # fmt: skip
        for value, n in Counter(c.get(field) or "" for c in in_scope).most_common():
            claim_rows.append({"field": field, "value": value, "rows": n})
    cov = defaultdict(Counter)
    for c in claims:
        if c.get("source") != "fact_check":
            continue
        k = c["fact_checker"]
        cov[k]["fact_checks"] += 1
        if c.get("in_scope") == "yes":
            cov[k]["in_scope"] += 1
            cov[k]["with_candidates"] += (c.get("claim_group") or c["claim_id"]) in matched
    coverage_rows = [{"fact_checker": k, **v} for k, v in sorted(cov.items())]

    lang = Counter("bangla" if is_bangla({"title": c.get("title", "")}) else "english"
                   for c in cands)  # fmt: skip
    cand_rows = [{"outlet": r["outlet"], "candidates": r["candidates"]} for r in outlet_rows
                 if r["candidates"]]  # fmt: skip

    summary = {
        "window": WINDOW,
        "outlets": len([r for r in outlet_rows if r["collected"]]),
        "articles_listed": sum(listed.values()),
        "articles_collected": len(articles),
        "articles_with_text": sum(r["with_text"] for r in outlet_rows),
        "articles_in_window": sum(r["in_window"] for r in outlet_rows),
        "articles_no_date": sum(r["no_date"] for r in outlet_rows),
        "matching_corpus": len(texts),
        "corpus_bangla": sum(1 for t in texts if is_bangla(t)),
        "claim_rows": len(claims),
        "claim_rows_in_scope": len(in_scope),
        "claim_groups": len(groups),
        "claim_groups_with_candidates": len(groups & matched),
        "ground_truth_ohchr": sum(
            1 for c in in_scope if c.get("ohchr_finding") in ("found", "contradicted")
        ),  # fmt: skip
        "candidate_pairs": len(cands),
        "candidate_languages": dict(lang),
    }
    tables = {"outlets": outlet_rows, "days": day_rows, "claims": claim_rows,
              "candidates": cand_rows, "coverage": coverage_rows}  # fmt: skip
    return summary, tables


def _write_tables(path: Path, tables: dict[str, list[dict]]) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in tables.items():
        ws = wb.create_sheet(name)
        if not rows:
            continue
        head = list(rows[0])
        ws.append(head)
        for c in ws[1]:
            c.font = Font(bold=True)
        for r in rows:
            ws.append([r.get(h, "") for h in head])
    wb.save(path)
