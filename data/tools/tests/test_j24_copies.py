"""Copy detection on SYNTHETIC articles: rewrites and agency feeds join, separate reports
do not, the check sheet hides the reason, and fusion can use the stories."""

import json

from openpyxl import load_workbook

from carcux_data.j24 import copies as cp
from carcux_data.j24.fusion import load_votes, stories

BASE = (
    "SYNTHETIC Police fired on students near the university gate on Thursday afternoon, "
    "witnesses said, and at least six people were taken to the medical college hospital. "
)
REWRITE = BASE.replace("Thursday afternoon", "Thursday").replace("at least six", "six")
OTHER = (
    "SYNTHETIC In a separate report from the district, shopkeepers described how the "
    "market stayed shut for a third day while traders counted their losses quietly."
)


def w(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")


def folder(tmp_path):
    arts = [
        ("u1", "a", "Students shot at gate", BASE * 3, "2024-07-18"),
        ("u2", "b", "Six hurt as police fire", REWRITE * 3, "2024-07-19"),
        ("u3", "c", "Market shut again", OTHER * 3, "2024-07-18"),
        ("u4", "d", "Protest news (BSS)", "BSS reports SYNTHETIC " + OTHER[:60] + BASE[:90],
         "2024-07-20"),
        ("u5", "e", "Rally update", "SYNTHETIC বাসস জানায় " + OTHER[:60] + BASE[:90], "2024-07-21"),
    ]  # fmt: skip
    w(tmp_path / "news" / "texts.jsonl",
      [{"url": u, "outlet": o, "title": t, "text": x, "published_at": d}
       for u, o, t, x, d in arts])  # fmt: skip
    w(tmp_path / "matches" / "candidates.jsonl",
      [{"claim_group": "g1", "url": u, "outlet": o, "title": t, "published_at": d}
       for u, o, t, _, d in arts])  # fmt: skip
    return arts


def test_rewrites_and_agency_feeds_join_separate_reports_do_not(tmp_path):
    folder(tmp_path)
    s = cp.detect(tmp_path, log=lambda m: None)
    rows = {r["url"]: r for r in map(json.loads, (tmp_path / "matches" / "copies.jsonl")
                                     .read_text("utf-8").splitlines())}  # fmt: skip
    assert rows["u1"]["story"] == rows["u2"]["story"]  # a rewrite
    assert rows["u2"]["is_copy"] and not rows["u1"]["is_copy"]  # the earlier one is the origin
    assert rows["u3"]["story"] != rows["u1"]["story"]  # a separate report
    assert rows["u4"]["story"] == rows["u5"]["story"]  # both credit BSS, similar text
    assert s["copies_text_rule"] >= 2 and s["agency_credits"]["BSS"] == 2


def test_check_sheet_hides_the_reason_and_scores(tmp_path):
    folder(tmp_path)
    cp.detect(tmp_path, log=lambda m: None)
    sheet = tmp_path / "matches" / "copies_check.xlsx"
    wb = load_workbook(sheet)
    ws = wb["Check"]
    head = [c.value for c in ws[1]]
    assert "reason" not in head and "cosine" not in head
    for row in ws.iter_rows(min_row=2):
        row[head.index("same_story")].value = "yes"
    wb.save(sheet)
    r = cp.score_sheet(sheet)
    assert r["judged"] >= 1
    if r["called_copy_judged"]:
        assert r["precision"] == 1.0


def test_fusion_uses_text_stories(tmp_path):
    folder(tmp_path)
    cp.detect(tmp_path, log=lambda m: None)
    feats = [{"pair_id": f"p{n:05d}", "claim_group": "g1", "sim_max": 0.95, "entail": 0.9,
              "contra": 0.0, "correct_cues": 0, "doubt_cues": 0} for n in range(1, 6)]  # fmt: skip
    w(tmp_path / "matches" / "stance_features.jsonl", feats)
    by_title = load_votes(tmp_path)["g1"]
    by_text = load_votes(tmp_path, copies="text")["g1"]
    assert len(set(stories(by_text))) < len(set(stories(by_title)))
    assert abs(sum(v["weight"] for v in by_text) - sum(v["weight"] for v in by_title)) > 0.1
