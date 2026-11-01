"""The Paper 2 statistics on a SYNTHETIC folder."""

import json

from openpyxl import load_workbook

from carcux_data.j24.stats import compute


def w(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")


def test_stats_counts_and_tables(tmp_path):
    w(
        tmp_path / "news" / "urls.jsonl",
        [{"outlet": "prothomalo", "url": "u1"}, {"outlet": "prothomalo", "url": "u2"}],
    )
    w(
        tmp_path / "news" / "articles_all.jsonl",
        [
            {
                "outlet": "prothomalo",
                "url": "u1",
                "text_chars": 900,
                "published_in_window": True,
                "about_uprising": True,
            },
            {"outlet": "prothomalo", "url": "u2", "text_chars": 10, "published_in_window": None},
        ],
    )
    w(
        tmp_path / "news" / "texts.jsonl",
        [
            {
                "outlet": "prothomalo",
                "url": "u1",
                "title": "SYNTHETIC কোটা আন্দোলন",
                "text": "লেখা",
                "published_at": "2024-07-18",
            }
        ],
    )
    w(
        tmp_path / "matches" / "candidates.jsonl",
        [{"claim_group": "c1", "outlet": "prothomalo", "title": "SYNTHETIC কোটা"}],
    )
    claims = tmp_path / "claims.jsonl"
    w(
        claims,
        [
            {
                "claim_id": "c1",
                "claim_group": "c1",
                "in_scope": "yes",
                "source": "fact_check",
                "fact_checker": "X",
                "verdict": "false",
            },
            {
                "claim_id": "c2",
                "claim_group": "c2",
                "in_scope": "no",
                "source": "fact_check",
                "fact_checker": "X",
            },
        ],
    )
    s = compute(tmp_path, claims)
    assert s["articles_collected"] == 2 and s["articles_with_text"] == 1
    assert s["claim_groups"] == 1 and s["claim_groups_with_candidates"] == 1
    wb = load_workbook(tmp_path / "stats" / "tables.xlsx")
    assert wb.sheetnames == ["outlets", "days", "claims", "candidates", "coverage"]
    assert wb["coverage"]["B2"].value == 2  # two fact-checks from X
