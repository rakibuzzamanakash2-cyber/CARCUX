"""The public release of CARCUX-J24, and a script to rebuild article text from it.

`build` writes release/ from the working folder:

- claims.jsonl: the claims in scope, with the fields a user needs (no review notes, no
  internal hints), the Bangla translation of each claim group, and evidence text cut to
  300 characters with social-media links removed.
- claim_groups.jsonl: each claim group, its members and its veracity label with the rule
  that gave it (or why it has none).
- articles.jsonl: the matching corpus as metadata only: link, archive copy, capture time,
  title, date and where the date came from, language and text length. No article text,
  because the outlets hold its copyright; `fulltext` rebuilds it.
- pairs.jsonl: the candidate claim-article pairs with their retrieval scores and, when the
  labelled sheets are given, each labeller's pseudonym and label and the gold label.
- outlets.csv: per outlet, country, language and the collection counts.
- splits.json: the fusion test claim groups and, with labels, the stance development groups.

`fulltext` reads release/articles.jsonl, fetches each archive copy politely and writes the
text the reader extracts to fulltext.jsonl, resuming where it stopped.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from carcux_data.j24.fusion import FALSE_VERDICTS, truth_labels
from carcux_data.j24.fusion import split as test_split
from carcux_data.j24.match import is_bangla
from carcux_data.j24.news import WAYBACK, read_article
from carcux_data.j24.stats import _jsonl, collect

CLAIM_FIELDS = ["claim_id", "claim_group", "source", "fact_checker", "url", "published_at",
                "claim", "claim_bn", "claim_type", "event_type", "place", "event_date",
                "verdict", "evidence_tier", "evidence_text", "ohchr_finding",
                "same_claim_as", "drafted_by", "checked_by"]  # fmt: skip
EXCERPT = 300
SOCIAL = re.compile(
    r"https?://(?:www\.|m\.|web\.)?(?:facebook|fb|twitter|x|youtube|youtu|tiktok|instagram|t)"
    r"\.(?:com|be|me|watch)/\S*",
    re.I,
)
HANDLE = re.compile(r"(?<![\w.])@[A-Za-z0-9_.]{3,}")


def article_id(url: str) -> str:
    return "a" + hashlib.sha1(url.encode()).hexdigest()[:12]  # noqa: S324 - an id, not security


def clean(text: str | None, limit: int | None = EXCERPT) -> str:
    """Social-media links and @handles removed, then cut to `limit` characters."""
    t = SOCIAL.sub("[social link removed]", text or "")
    t = HANDLE.sub("[handle removed]", t)
    t = " ".join(t.split())
    return t if limit is None or len(t) <= limit else t[: limit - 1].rstrip() + "…"


def _group_label(rows: list[dict]) -> tuple[int | None, str]:
    """The veracity label of one claim group and the rule behind it (as fusion.truth_labels)."""
    votes = []
    for r in rows:
        if r["source"] == "ohchr":
            if r.get("ohchr_finding") == "found":
                votes.append((1, "OHCHR found"))
            elif r.get("ohchr_finding") == "contradicted":
                votes.append((0, "OHCHR contradicted"))
        elif r.get("verdict") in FALSE_VERDICTS:
            votes.append((0, f"fact-check {r['verdict']}"))
        elif r.get("verdict") == "true":
            votes.append((1, "fact-check true"))
    if not votes:
        return None, "no verdict (relayed, unproven or cannot confirm)"
    if len({v for v, _ in votes}) > 1:
        return None, "conflicting verdicts"
    return votes[0][0], "; ".join(sorted({why for _, why in votes}))


def build(out: Path, claims_path: Path, claims_bn: Path | None = None, *,
          sheets: list[Path] | None = None, key: Path | None = None,
          log: Callable[[str], None] = print) -> dict:  # fmt: skip
    folder = out / "release"
    folder.mkdir(exist_ok=True)
    claims = [c for c in _jsonl(claims_path) if c.get("in_scope") == "yes"]
    bn = {r["claim_group"]: r.get("claim_bn", "") for r in _jsonl(claims_bn)} if claims_bn else {}
    removed = Counter()

    rows = []
    for c in claims:
        g = c.get("claim_group") or c["claim_id"]
        r = {f: c.get(f, "") for f in CLAIM_FIELDS}
        r["claim_group"], r["claim_bn"] = g, bn.get(g, "")
        for f in ("claim", "claim_bn", "place"):
            r[f] = clean(r[f], None)
        before = c.get("evidence_text") or ""
        r["evidence_text"] = clean(before)
        removed["social links or handles"] += bool(SOCIAL.search(before) or HANDLE.search(before))
        rows.append(r)
    _write(folder / "claims.jsonl", rows)

    by_group: dict[str, list[dict]] = {}
    for c in claims:
        by_group.setdefault(c.get("claim_group") or c["claim_id"], []).append(c)
    truth = truth_labels(claims_path)
    groups = []
    for g, members in sorted(by_group.items()):
        label, basis = _group_label(members)
        if label != truth.get(g):  # one rule, two places: they must agree
            raise ValueError(f"veracity rule mismatch for {g}")
        groups.append({"claim_group": g, "claims": [m["claim_id"] for m in members],
                       "label": {1: "true", 0: "false"}.get(label), "basis": basis})  # fmt: skip
    _write(folder / "claim_groups.jsonl", groups)

    captures = {a["url"]: a for a in _jsonl(out / "news" / "articles_all.jsonl")}
    articles = []
    for t in _jsonl(out / "news" / "texts.jsonl"):
        a = captures.get(t["url"], {})
        cap = a.get("capture")
        articles.append({
            "article_id": article_id(t["url"]), "outlet": t["outlet"], "url": t["url"],
            "archive_url": f"{WAYBACK}/{cap}/{t['url']}" if cap else None,
            "capture": cap, "capture_late": a.get("capture_late"),
            "title": clean(t.get("title"), None), "published_at": t.get("published_at"),
            "published_source": a.get("published_source") or t.get("published_source"),
            "language": "bn" if is_bangla(t) else "en",
            "text_chars": a.get("text_chars") or len(t.get("text") or ""),
        })  # fmt: skip
    _write(folder / "articles.jsonl", articles)
    known = {a["url"] for a in articles}

    labels, gold, shared = {}, {}, set()
    if sheets and key:
        from carcux_data.j24.stance import read_sheets

        k = json.loads(key.read_text("utf-8"))
        examples = set(k.get("examples", {}))
        shared = {e["pair_id"] for e in k["key"] if e["overlap"]}
        labels = read_sheets(sheets)
        for pid, given in labels.items():
            if pid in examples:
                continue
            counts = Counter(lab for _, lab in given).most_common()
            if len(counts) == 1 or counts[0][1] > counts[1][1]:
                gold[pid] = counts[0][0]
    pairs = []
    for n, c in enumerate(_jsonl(out / "matches" / "candidates.jsonl"), start=1):
        pid = c.get("pair_id") or f"p{n:05d}"
        p = {"pair_id": pid, "claim_group": c["claim_group"], "article_id": article_id(c["url"]),
             "in_corpus": c["url"] in known, "rank": c.get("rank"), "bm25": c.get("bm25"),
             "cosine": c.get("cosine"), "fused": c.get("fused")}  # fmt: skip
        if labels:
            p["labels"] = [{"annotator": a, "stance": s} for a, s in labels.get(pid, [])]
            p["shared"] = pid in shared
            p["gold"] = gold.get(pid)
        pairs.append(p)
    _write(folder / "pairs.jsonl", pairs)

    _, tables = collect(out, claims_path)
    outlet_rows = [r for r in tables["outlets"] if r["collected"]]
    if outlet_rows:
        with (folder / "outlets.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(outlet_rows[0]))
            w.writeheader()
            w.writerows(outlet_rows)

    splits = {"seed": 2024, "fusion_test_groups": sorted(test_split(list(truth)))}
    if gold:
        from carcux_data.j24.stance import split as dev_split

        cg = {p["pair_id"]: p["claim_group"] for p in pairs}
        splits["stance_dev_groups"] = sorted(dev_split([cg[p] for p in gold if p in cg]))
    (folder / "splits.json").write_text(json.dumps(splits, indent=1), encoding="utf-8")

    problems = privacy_problems(folder)
    summary = {"claims": len(rows), "claim_groups": len(groups),
               "labelled_groups": sum(g["label"] is not None for g in groups),
               "articles": len(articles),
               "articles_without_capture": sum(a["archive_url"] is None for a in articles),
               "pairs": len(pairs), "pairs_with_gold": len(gold),
               "evidence_cleaned": dict(removed), "privacy_problems": problems}  # fmt: skip
    log(json.dumps(summary, indent=1, ensure_ascii=False))
    return summary


def privacy_problems(folder: Path) -> list[str]:
    """Anything in the release files that should not be public; empty when all is well."""
    found = []
    for path in sorted(folder.glob("*.jsonl")):
        for n, line in enumerate(path.read_text("utf-8").splitlines(), start=1):
            r = json.loads(line)
            for k in r:
                if k in {"text", "snippet", "review_note", "handle", "account"}:
                    found.append(f"{path.name}:{n} has a field '{k}'")
            body = json.dumps({k: v for k, v in r.items() if k not in {"url", "archive_url"}},
                              ensure_ascii=False)  # fmt: skip
            if SOCIAL.search(body) or HANDLE.search(body):
                found.append(f"{path.name}:{n} has a social-media link or handle")
    return found


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")


def fulltext(release: Path, target: Path, *, fetcher=None, limit: int | None = None,
             log: Callable[[str], None] = print) -> dict:  # fmt: skip
    """Rebuild article text from the archive copies listed in the release."""
    if fetcher is None:
        from carcux_data.j24.fetch import Fetcher

        fetcher = Fetcher(target.parent / "fulltext_cache", delay=4.0)
    done = {r["article_id"] for r in _jsonl(target)}
    counts = Counter(already=len(done))
    todo = [a for a in _jsonl(release / "articles.jsonl") if a["article_id"] not in done]
    with target.open("a", encoding="utf-8") as f:
        for n, a in enumerate(todo[:limit] if limit else todo, start=1):
            if not a.get("archive_url"):
                counts["no_capture"] += 1
                continue
            src = a["archive_url"].replace(f"/{a['capture']}/", f"/{a['capture']}id_/", 1)
            try:
                status, body, _ = fetcher.get_page(src)
            except OSError:
                counts["failed"] += 1
                continue
            if not status or status >= 400 or not body:
                counts["failed"] += 1
                continue
            art = read_article(body, with_text=True)
            f.write(json.dumps({"article_id": a["article_id"], "url": a["url"],
                                "title": art["title"] or a["title"], "text": art.get("text", "")},
                               ensure_ascii=False) + "\n")  # fmt: skip
            counts["written"] += 1
            if n % 100 == 0:
                log(f"  {n} of {len(todo)} done")
    return dict(counts)
