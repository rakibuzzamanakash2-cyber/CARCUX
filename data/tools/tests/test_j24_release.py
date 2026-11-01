"""The public release and the bootstrap intervals, on a SYNTHETIC folder."""

import json

from carcux_data.j24.ci import interval
from carcux_data.j24.release import article_id, build, clean, fulltext, privacy_problems


def w(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")


def read(path):
    return [json.loads(x) for x in path.read_text("utf-8").splitlines()]


def folder(tmp_path):
    w(tmp_path / "news" / "urls.jsonl", [{"outlet": "prothomalo", "url": "https://p/1"}])
    w(tmp_path / "news" / "articles_all.jsonl", [{
        "outlet": "prothomalo", "url": "https://p/1", "capture": "20240719010203",
        "capture_late": False, "text_chars": 900, "published_in_window": True,
        "published_source": "page_field"}])  # fmt: skip
    w(tmp_path / "news" / "texts.jsonl", [{
        "outlet": "prothomalo", "url": "https://p/1", "title": "SYNTHETIC কোটা সংস্কার আন্দোলনের খবর",
        "text": "SYNTHETIC লেখা আন্দোলনের খবর " * 40, "published_at": "2024-07-18"}])  # fmt: skip
    w(tmp_path / "matches" / "candidates.jsonl", [{
        "pair_id": "p00001", "claim_group": "g1", "rank": 1, "url": "https://p/1",
        "outlet": "prothomalo", "title": "SYNTHETIC", "bm25": 1.0, "cosine": 0.8,
        "fused": 0.03, "snippet": "SYNTHETIC full sentence from the article"}])  # fmt: skip
    claims = tmp_path / "claims.jsonl"
    base = {"in_scope": "yes", "source": "fact_check", "fact_checker": "X",
            "review_note": "private note"}  # fmt: skip
    w(claims, [
        {**base, "claim_id": "c1", "claim_group": "g1", "verdict": "false",
         "claim": "SYNTHETIC claim",
         "evidence_text": "see https://facebook.com/someone and @handle_x"},
        {**base, "claim_id": "c2", "claim_group": "g1", "verdict": "misleading"},
        {**base, "claim_id": "c3", "claim_group": "g2", "verdict": "true"},
        {**base, "claim_id": "c4", "claim_group": "g2", "verdict": "false"},
        {**base, "claim_id": "c5", "claim_group": "g3", "source": "ohchr", "verdict": "",
         "ohchr_finding": "relayed"},
        {**base, "claim_id": "c6", "claim_group": "g4", "in_scope": "no"},
    ])  # fmt: skip
    bn = tmp_path / "claims_bn.jsonl"
    w(bn, [{"claim_group": "g1", "claim_en": "SYNTHETIC claim", "claim_bn": "SYNTHETIC দাবি"}])
    return claims, bn


def test_release_files_hold_no_text_and_no_private_fields(tmp_path):
    claims, bn = folder(tmp_path)
    s = build(tmp_path, claims, bn, log=lambda m: None)
    rel = tmp_path / "release"
    assert s["privacy_problems"] == []
    assert s["claims"] == 5 and s["claim_groups"] == 3
    c = read(rel / "claims.jsonl")
    assert "review_note" not in c[0] and c[0]["claim_bn"] == "SYNTHETIC দাবি"
    assert "facebook" not in c[0]["evidence_text"] and "@handle_x" not in c[0]["evidence_text"]
    g = {r["claim_group"]: r for r in read(rel / "claim_groups.jsonl")}
    assert g["g1"]["label"] == "false" and "misleading" in g["g1"]["basis"]
    assert g["g2"]["label"] is None and g["g2"]["basis"] == "conflicting verdicts"
    assert g["g3"]["label"] is None
    a = read(rel / "articles.jsonl")[0]
    assert "text" not in a and a["language"] == "bn"
    assert a["archive_url"] == "https://web.archive.org/web/20240719010203/https://p/1"
    p = read(rel / "pairs.jsonl")[0]
    assert p["article_id"] == article_id("https://p/1") and "snippet" not in p
    assert (rel / "outlets.csv").read_text("utf-8").startswith("outlet,")
    assert json.loads((rel / "splits.json").read_text("utf-8"))["seed"] == 2024


def test_privacy_check_catches_leaks(tmp_path):
    w(tmp_path / "x.jsonl", [{"title": "see @someone_here"}, {"text": "full article"}])
    assert len(privacy_problems(tmp_path)) == 2


def test_clean_cuts_to_300():
    assert len(clean("ক" * 1000)) == 300


def test_fulltext_resumes_and_skips_missing(tmp_path):
    rel = tmp_path / "release"
    w(rel / "articles.jsonl", [
        {"article_id": "a1", "url": "https://p/1", "capture": "20240719010203", "title": "t",
         "archive_url": "https://web.archive.org/web/20240719010203/https://p/1"},
        {"article_id": "a2", "url": "https://p/2", "capture": None, "archive_url": None,
         "title": "t"},
    ])  # fmt: skip
    asked = []

    class Fake:
        def get_page(self, url):
            asked.append(url)
            html = (
                "<html><head><title>SYNTHETIC</title></head><body><article><p>"
                + "SYNTHETIC text. " * 40
                + "</p></article></body></html>"
            )
            return 200, html.encode(), url

    target = rel / "fulltext.jsonl"
    r = fulltext(rel, target, fetcher=Fake(), log=lambda m: None)
    assert r["written"] == 1 and r["no_capture"] == 1
    assert asked == ["https://web.archive.org/web/20240719010203id_/https://p/1"]
    assert fulltext(rel, target, fetcher=Fake(), log=lambda m: None)["already"] == 1
    assert len(asked) == 1


def test_interval_brackets_the_mean():
    lo, hi = interval(list(range(100)), lambda xs: sum(xs) / len(xs))
    assert lo < 49.5 < hi
    assert interval([1], lambda xs: 1.0) is None
