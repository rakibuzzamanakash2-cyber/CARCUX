"""Which candidate articles of a claim are really one story (copies, rewrites, agency feeds).

The fusion's title rule only joins near-identical headlines. Outlets in Bangladesh often
rewrite an agency report (BSS, UNB) or each other in their own words, so here the text is
compared as well. For the articles of one claim group:

- **text:** cosine similarity of character 4-gram counts over the first 2,000 characters
  (works the same for Bangla and English, and survives small edits);
- **agency credit:** both articles name the same news agency;
- **title:** the fusion's title rule (60% shared words).

Two articles are one story if the cosine is at least `THRESHOLD`, or they credit the same
agency and the cosine is at least `AGENCY_FLOOR`, or the title rule joins them. Stories are
the connected groups; each story's origin is its earliest article.

Limits: an English rewrite of a Bangla report shares no character n-grams and is missed
unless both credit the same agency; two eyewitness accounts that read alike would be
joined. The check sheet measures how often each happens.
"""

from __future__ import annotations

import json
import math
import random
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path

from carcux_data.j24.fusion import COPY_JACCARD, _title_words
from carcux_data.j24.stats import _jsonl

THRESHOLD = 0.6  # the platform detector's default, not tuned on J24
AGENCY_FLOOR = 0.3
CHARS = 2000
NEAR = (0.35, THRESHOLD)  # near misses shown on the check sheet
SEED = 2024
AGENCIES = {
    "BSS": r"\bBSS\b|বাসস",
    "UNB": r"\bUNB\b|ইউএনবি",
    "AFP": r"\bAFP\b|এএফপি",
    "Reuters": r"Reuters|রয়টার্স|রয়টার্স",
    "AP": r"\bAP\b|Associated Press|অ্যাসোসিয়েটেড প্রেস",
    "PTI": r"\bPTI\b|পিটিআই",
    "IANS": r"\bIANS\b|আইএএনএস",
    "ANI": r"\bANI\b|এএনআই",
}
_AGENCY = {k: re.compile(v) for k, v in AGENCIES.items()}


def grams(text: str, n: int = 4) -> Counter:
    t = " ".join((text or "").lower().split())[:CHARS]
    return Counter(t[i : i + n] for i in range(max(len(t) - n + 1, 0)))


def cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    dot = sum(v * b.get(k, 0) for k, v in a.items())
    return dot / math.sqrt(sum(v * v for v in a.values()) * sum(v * v for v in b.values()))


def agencies(text: str) -> set[str]:
    return {k for k, rx in _AGENCY.items() if rx.search(text or "")}


def _title_join(a: str, b: str) -> bool:
    x, y = _title_words(a), _title_words(b)
    return bool(x and y and len(x & y) / len(x | y) >= COPY_JACCARD)


def pair_reason(a: dict, b: dict, cos: float) -> str | None:
    if cos >= THRESHOLD:
        return "text"
    shared = a["agencies"] & b["agencies"]
    if shared and cos >= AGENCY_FLOOR:
        return "agency:" + ",".join(sorted(shared))
    if _title_join(a.get("title", ""), b.get("title", "")):
        return "title"
    return None


def detect(out: Path, *, log: Callable[[str], None] = print) -> dict:
    texts = {t["url"]: t for t in _jsonl(out / "news" / "texts.jsonl")}
    cands = _jsonl(out / "matches" / "candidates.jsonl")
    for n, c in enumerate(cands, start=1):
        c.setdefault("pair_id", f"p{n:05d}")
        t = texts.get(c["url"], {})
        body = t.get("text") or ""
        c["grams"] = grams(f"{c.get('title') or ''} {body}")
        c["agencies"] = agencies(body)
        c["has_text"] = bool(body)
    by_claim: dict[str, list[dict]] = defaultdict(list)
    for c in cands:
        by_claim[c["claim_group"]].append(c)

    rows, pairs = [], []
    reasons = Counter()
    for g, arts in by_claim.items():
        parent = list(range(len(arts)))

        def find(i: int, parent: list[int] = parent) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        best = [0.0] * len(arts)
        for i in range(len(arts)):
            for j in range(i + 1, len(arts)):
                cos = cosine(arts[i]["grams"], arts[j]["grams"])
                best[i], best[j] = max(best[i], cos), max(best[j], cos)
                why = pair_reason(arts[i], arts[j], cos)
                pairs.append((g, arts[i], arts[j], cos, why))
                if why:
                    reasons[why.split(":")[0]] += 1
                    parent[find(i)] = find(j)
        groups: dict[int, list[int]] = defaultdict(list)
        for i in range(len(arts)):
            groups[find(i)].append(i)
        for members in groups.values():
            order = sorted(members, key=lambda i: (arts[i].get("published_at") or "9999",
                                                   arts[i]["pair_id"]))  # fmt: skip
            origin = arts[order[0]]["pair_id"]
            for i in members:
                a = arts[i]
                rows.append({"pair_id": a["pair_id"], "claim_group": g, "url": a["url"],
                             "outlet": a["outlet"], "story": f"{g}#{origin}",
                             "is_copy": a["pair_id"] != origin, "origin": origin,
                             "story_size": len(members), "best_cosine": round(best[i], 3),
                             "agencies": sorted(a["agencies"]),
                             "has_text": a["has_text"]})  # fmt: skip

    folder = out / "matches"
    folder.mkdir(exist_ok=True)
    rows.sort(key=lambda r: r["pair_id"])
    (folder / "copies.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    write_check_sheet(folder / "copies_check.xlsx", pairs)

    copies = [r for r in rows if r["is_copy"]]
    title_only = _title_only_count(by_claim)
    by_outlet = Counter(r["outlet"] for r in copies)
    totals = Counter(r["outlet"] for r in rows)
    summary = {
        "articles": len(rows),
        "articles_with_text": sum(r["has_text"] for r in rows),
        "copies_text_rule": len(copies),
        "copies_share": round(len(copies) / max(len(rows), 1), 4),
        "copies_title_rule_alone": title_only,
        "claims_with_a_copy": len({r["claim_group"] for r in copies}),
        "independent_stories": len({r["story"] for r in rows}),
        "pair_reasons": dict(reasons),
        "agency_credits": dict(Counter(a for r in rows for a in r["agencies"])),
        "copy_share_by_outlet": {
            o: round(by_outlet[o] / totals[o], 3) for o, _ in totals.most_common()
        },  # fmt: skip
    }
    text = json.dumps(summary, indent=1, ensure_ascii=False)
    (folder / "copies_summary.json").write_text(text, "utf-8")
    log(json.dumps({k: v for k, v in summary.items() if k != "copy_share_by_outlet"},
                   indent=1, ensure_ascii=False))  # fmt: skip
    return summary


def _title_only_count(by_claim: dict[str, list[dict]]) -> int:
    from carcux_data.j24.fusion import copy_clusters

    n = 0
    for arts in by_claim.values():
        c = copy_clusters([{"title": a.get("title") or ""} for a in arts])
        n += len(arts) - len(set(c))
    return n


def write_check_sheet(path: Path, pairs: list[tuple]) -> None:
    """60 pairs called copies and 60 near misses, shuffled together, without the detector's
    reason or score, for a person to judge: same story or not."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    rng = random.Random(SEED)  # noqa: S311 - a reproducible sample, not security
    called = [p for p in pairs if p[4]]
    near = [p for p in pairs if not p[4] and NEAR[0] <= p[3] < NEAR[1]]
    sample = rng.sample(called, min(60, len(called))) + rng.sample(near, min(60, len(near)))
    rng.shuffle(sample)
    wb = Workbook()
    ws = wb.active
    ws.title = "Check"
    head = ["check_id", "claim_group", "outlet_A", "date_A", "title_A", "url_A",
            "outlet_B", "date_B", "title_B", "url_B", "same_story", "note"]  # fmt: skip
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F5F3A")
    key = []
    for n, (g, a, b, cos, why) in enumerate(sample, start=1):
        cid = f"c{n:03d}"
        ws.append([cid, g, a["outlet"], (a.get("published_at") or "")[:10], a.get("title"),
                   a["url"], b["outlet"], (b.get("published_at") or "")[:10], b.get("title"),
                   b["url"], "", ""])  # fmt: skip
        key.append({"check_id": cid, "called_copy": bool(why), "reason": why,
                    "cosine": round(cos, 3)})  # fmt: skip
    for col, w in zip("ABCDEFGHIJKL", (8, 10, 14, 11, 50, 30, 14, 11, 50, 30, 12, 24),
                      strict=True):  # fmt: skip
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    dv = DataValidation(type="list", formula1='"yes,no,unsure"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"K2:K{len(sample) + 1}")
    guide = wb.create_sheet("How to judge")
    for line in [
        "For each row, open both links and decide: are A and B the same story?",
        "yes = one is a copy, a rewrite or an agency feed of the other (same facts, same "
        "source, mostly the same sentences or order), even if the wording or headline differs.",
        "no = two separately reported articles about the same event (different reporting, "
        "quotes, details or angle).",
        "unsure = cannot tell. Do not guess.",
        "The sheet does not show why a pair was chosen; please do not look it up.",
    ]:
        guide.append([line])
    guide.column_dimensions["A"].width = 120
    wb.save(path)
    path.with_name("copies_check_key.json").write_text(json.dumps(key, indent=1), "utf-8")


def score_sheet(sheet: Path) -> dict:
    """Precision of the detector and the share of near misses that are copies, from a
    judged check sheet and its key (written next to it)."""
    from openpyxl import load_workbook

    key = {k["check_id"]: k for k in json.loads(
        sheet.with_name("copies_check_key.json").read_text("utf-8"))}  # fmt: skip
    ws = load_workbook(sheet, read_only=True).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    head = list(rows[0])
    judged = {}
    for r in rows[1:]:
        d = dict(zip(head, r, strict=False))
        v = str(d.get("same_story") or "").strip().lower()
        if d.get("check_id") in key and v in ("yes", "no"):
            judged[d["check_id"]] = v == "yes"
    called = [judged[c] for c in judged if key[c]["called_copy"]]
    near = [judged[c] for c in judged if not key[c]["called_copy"]]
    return {
        "judged": len(judged),
        "called_copy_judged": len(called),
        "precision": round(sum(called) / len(called), 3) if called else None,
        "near_miss_judged": len(near),
        "near_misses_that_are_copies": round(sum(near) / len(near), 3) if near else None,
    }
