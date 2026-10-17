"""How often outlets recur across fact-checks: the pilot's go / no-go numbers.

A fact-check citing an outlet means the outlet was involved in that claim, either as
a source of the claim or as evidence about it. It is an upper bound on how often each
outlet reported on a claim; the claim sheet and stance annotation settle which.
Thresholds are the protocol's (research/j24/PROTOCOL.md, section 9).
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

GO = {"claims": 250, "recurring_sources": 20, "min_claims_per_source": 5}


def load(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def summarise(records: list[dict], *, in_scope_only: bool = True) -> dict:
    rows = [r for r in records if r["scope_hint"]] if in_scope_only else records
    by_source: dict[str, set[str]] = defaultdict(set)
    names: dict[str, str] = {}
    kinds: dict[str, str] = {}
    countries: dict[str, str | None] = {}
    unregistered: Counter = Counter()
    for r in rows:
        for c in r["cited"]:
            if c["kind"] in ("archive", "tool"):
                continue
            if c["kind"] == "other":
                unregistered[c["domain"]] += 1
                continue
            by_source[c["domain"]].add(r["factcheck_id"])
            names[c["domain"]] = c["outlet"] or c["domain"]
            kinds[c["domain"]] = c["kind"]
            countries[c["domain"]] = c.get("country")
    counts = sorted(((len(v), d) for d, v in by_source.items()), reverse=True)
    recurring = [d for n, d in counts if n >= GO["min_claims_per_source"]]
    per_claim = [
        sum(1 for c in r["cited"] if c["kind"] not in ("archive", "tool", "other")) for r in rows
    ]
    social = sum(len(r["social_links"]) for r in rows)
    sites = Counter(r["site"] for r in rows)
    verdicts = Counter(r["verdict_hint"] or "none found" for r in rows)
    return {
        "factchecks": len(rows),
        "factchecks_all": len(records),
        "by_site": dict(sites),
        "verdict_hints": dict(verdicts),
        "sources": len(by_source),
        "recurring_sources": len(recurring),
        "sources_per_factcheck_median": sorted(per_claim)[len(per_claim) // 2] if per_claim else 0,
        "social_links": social,
        "top_sources": [
            {
                "domain": d,
                "name": names[d],
                "kind": kinds[d],
                "country": countries[d],
                "factchecks": n,
            }
            for n, d in counts[:40]
        ],  # fmt: skip
        "unregistered_domains": unregistered.most_common(40),
    }


def report(s: dict) -> str:
    lines = [
        "CARCUX-J24 pilot: fact-checks and recurring sources",
        "",
        f"Fact-checks in the window: {s['factchecks_all']}; likely about the uprising "
        f"(scope hint): {s['factchecks']}",
        "By fact-checker: " + ", ".join(f"{k} {v}" for k, v in sorted(s["by_site"].items())),
        "Verdict words found: " + ", ".join(f"{k} {v}" for k, v in s["verdict_hints"].items()),
        f"Distinct outlets and official sites cited: {s['sources']}",
        f"Cited by {GO['min_claims_per_source']} or more fact-checks: {s['recurring_sources']}",
        f"Median outlets cited per fact-check: {s['sources_per_factcheck_median']}",
        f"Links to social media posts (kept in restricted/): {s['social_links']}",
        "",
        "Go / no-go (claims are counted after the claim sheet removes duplicates; this is "
        "an upper bound):",
        f"  fact-checks >= {GO['claims']}: "
        f"{'yes' if s['factchecks'] >= GO['claims'] else 'NOT YET'} ({s['factchecks']})",
        f"  sources cited by >= {GO['min_claims_per_source']}: "
        f"{'yes' if s['recurring_sources'] >= GO['recurring_sources'] else 'NOT YET'} "
        f"({s['recurring_sources']} of {GO['recurring_sources']} needed)",
        "",
        "Most cited (fact-checks citing each):",
    ]
    for t in s["top_sources"]:
        lines.append(f"  {t['factchecks']:4d}  {t['name']} ({t['domain']}, {t['kind']})")
    if s["unregistered_domains"]:
        lines += ["", "Domains not in outlets.csv yet (add the real outlets, ignore the rest):"]
        lines += [f"  {n:4d}  {d}" for d, n in s["unregistered_domains"]]
    return "\n".join(lines) + "\n"
