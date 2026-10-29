"""The stance baseline with stand-in models, the decision rule, agreement and the split.
Every claim, article and label below is SYNTHETIC."""

import json

from openpyxl import Workbook

from carcux_data.j24 import stance as st


def test_sentences_and_candidates_keep_the_closest_sentences():
    art = {
        "title": "শিরোনাম",
        "text": "SYNTHETIC বিমানবন্দর বন্ধের খবরটি ভুয়া বলে জানা গেছে। "
        "আজ আবহাওয়া ভালো ছিল এবং বৃষ্টি হয়নি। " * 3,
    }
    got = st.candidate_sentences("শাহজালাল বিমানবন্দর বন্ধ", art, k=1)
    assert got[0] == "শিরোনাম" and "বিমানবন্দর" in got[1]


def test_predict_follows_the_guide_order():
    base = {"sim_max": 0.9, "entail": 0.1, "contra": 0.1, "correct_cues": 0, "doubt_cues": 0}
    assert st.predict({**base, "sim_max": 0.5}) == "unrelated"
    assert st.predict({**base, "contra": 0.9, "correct_cues": 2}) == "corrects"
    assert st.predict({**base, "entail": 0.9, "doubt_cues": 1}) == "questions"
    assert st.predict({**base, "entail": 0.9}) == "repeats"
    assert st.predict(base) == "mentions"
    assert st.predict({**base, "correct_cues": 9}, {**st.DEFAULTS, "strong": 5}) == "corrects"


def test_score_with_stand_in_models(tmp_path):
    (tmp_path / "news").mkdir()
    (tmp_path / "matches").mkdir()
    art = {
        "url": "u1",
        "outlet": "p",
        "title": "Airport rumour is fake",
        "text": "SYNTHETIC The report that the airport was closed is fake. Other news.",
        "published_at": "2024-07-16",
    }
    (tmp_path / "news" / "texts.jsonl").write_text(json.dumps(art) + "\n", encoding="utf-8")
    (tmp_path / "matches" / "candidates.jsonl").write_text(
        json.dumps({"claim_group": "c1", "url": "u1", "title": art["title"]}) + "\n",
        encoding="utf-8",
    )
    wb = Workbook()
    ws = wb.active
    ws.title = "Candidates"
    ws.append(["pair_id", "claim_group", "claim"])
    ws.append(["p00001", "c1", "The airport was closed for 72 hours."])
    wb.save(tmp_path / "matches" / "candidates.xlsx")
    rows = st.score(
        tmp_path,
        embed=lambda c, s: [0.9] * len(s),
        infer=lambda pairs: (
            [{"entailment": 0.1, "neutral": 0.1, "contradiction": 0.8}] * len(pairs)
        ),
        log=lambda m: None,
    )
    assert rows[0]["pair_id"] == "p00001" and rows[0]["correct_cues"] >= 1
    assert st.predict(rows[0]) == "corrects"


def test_alpha_is_one_for_full_agreement_and_lower_otherwise():
    assert st.krippendorff_nominal([["a", "a"], ["b", "b"], ["a", "a"]]) == 1.0
    assert st.krippendorff_nominal([["a", "b"], ["b", "a"], ["a", "a"]]) < 0.5


def test_split_is_fixed_and_by_claim():
    groups = [f"g{i}" for i in range(50)]
    assert st.split(groups) == st.split(list(reversed(groups)))
    assert len(st.split(groups)) == 10


def test_fit_never_sees_test_and_beats_nothing_on_easy_data():
    feats = [
        {"sim_max": 0.95, "entail": 0.9, "contra": 0.0, "correct_cues": 0, "doubt_cues": 0},
        {"sim_max": 0.5, "entail": 0.0, "contra": 0.0, "correct_cues": 0, "doubt_cues": 0},
    ]
    p = st.fit(feats, ["repeats", "unrelated"])
    assert [st.predict(f, p) for f in feats] == ["repeats", "unrelated"]
