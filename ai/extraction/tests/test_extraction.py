import json

import pytest

from carcux_extraction import detect_language, extract, numbers
from carcux_extraction.evaluate import agrees, dev_examples, main, score


def got(text: str) -> dict:
    return {c.attribute: c.value for c in extract(text)}


# --- Language ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("মিরপুরে হাঁটুসমান পানি", "bn"),
        ("Mirpur 10 e hatu pani, gari choltese na", "bn-Latn"),
        ("Knee-deep water at Mirpur 10 after heavy rain", "en"),
        ("Mirpur e waterlogging, হাঁটু পানি, cars stuck", "mixed"),
        ("ঢাকা DNCC এলাকায় জলাবদ্ধতা", "bn"),  # one Latin name does not make it mixed
        ("Dhaka", "en"),
    ],
)
def test_language(text, language):
    assert detect_language(text) == language


# --- Numbers -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("phrase", "n"),
    [
        ("1,250", 1250),
        ("১২৫০", 1250),
        ("12,50,000", 1_250_000),
        ("1.5 lakh", 150_000),
        ("দেড় লাখ", 150_000),
        ("tin hajar", 3000),
        ("two dozen", 24),
        ("তিন", 3),
        ("hundreds", None),
        ("কয়েকশ", None),
        ("koyek", None),
    ],
)
def test_numbers(phrase, n):
    assert numbers.value(phrase) == n


# --- Details -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Three people were killed in the collision", {"casualty_count": 3}),
        ("তিনজন নিহত", {"casualty_count": 3}),
        ("৫ জনের মৃত্যু", {"casualty_count": 5}),
        ("2 jon mara geche", {"casualty_count": 2}),
        ("Death toll rises to 12", {"casualty_count": 12}),
        ("No casualties were reported", {"casualty_count": 0}),
        ("কেউ হতাহত হয়নি", {"casualty_count": 0}),
        ("keu mara jay nai", {"casualty_count": 0}),
    ],
)
def test_deaths(text, expected):
    assert {k: v for k, v in got(text).items() if k in expected} == expected


@pytest.mark.parametrize(
    "text",
    [
        "Ten people injured as a microbus overturned",
        "অগ্নিকাণ্ডে আহত হয়েছেন ২০ জন",
        "koyekjon ahoto",
        "Hundreds of people were displaced",
        "কয়েকশ পরিবার আশ্রয়কেন্দ্রে উঠেছে",
    ],
)
def test_injuries_and_vague_amounts_are_not_counts(text):
    assert not {"casualty_count", "affected_count"} & set(got(text))


def test_a_count_does_not_reach_across_a_clause():
    assert got("সড়ক দুর্ঘটনায় একজন নিহত, তিনজন আহত।")["casualty_count"] == 1


def test_affected_with_units():
    [c] = [c for c in extract("প্রায় ৫০০ পরিবার পানিবন্দী") if c.attribute == "affected_count"]
    assert (c.value, c.unit) == (500, "households")
    [c] = [c for c in extract("1.5 lakh people marooned") if c.attribute == "affected_count"]
    assert (c.value, c.unit) == (150_000, "people")
    assert got("prai 300 poribar pani bondi")["affected_count"] == 300


@pytest.mark.parametrize(
    ("text", "depth"),
    [
        ("knee-deep water", "knee-deep"),
        ("water up to the waist", "waist-deep"),
        ("হাঁটুসমান পানি", "knee-deep"),
        ("কোমর পানি", "waist-deep"),
        ("Uttara te gorali pani", "ankle-deep"),
        ("buk pani", "chest-deep"),
        ("মাথার ওপর পানি", "above-head"),
        ("A massive fire at Bangabazar", "large"),
    ],
)
def test_magnitude(text, depth):
    assert got(text)["magnitude"] == depth


def test_body_parts_without_water_are_not_depths():
    assert "magnitude" not in got("হাঁটুতে ব্যথা, বুক ধড়ফড় করছে")
    assert "magnitude" not in got("he hurt his knee")


@pytest.mark.parametrize(
    ("text", "cause"),
    [
        ("Knee-deep water after heavy overnight rain", "heavy rain"),
        ("টানা বৃষ্টিতে জলাবদ্ধতা", "heavy rain"),
        ("bhari brishtir karone pani", "heavy rain"),
        ("Fire started from an electrical short circuit", "electrical short circuit"),
        ("শর্ট সার্কিট থেকে আগুন", "electrical short circuit"),
        ("cause: gas leak", "gas leak"),
        ("বাঁধ ভেঙে গ্রাম প্লাবিত", "embankment breach"),
        ("ujaner dhole buk pani", "upstream runoff"),
        ("andoloner karone mor bondho", "protest"),
        ("The cause is not yet known", "unknown"),
    ],
)
def test_cause(text, cause):
    assert got(text)["cause"] == cause


@pytest.mark.parametrize(
    "text",
    [
        "Heavy rain continues in Chattogram",  # rain is the event, not a cause
        "Protest at Shahbag",
        "নদীর পানি বিপৎসীমার ওপর দিয়ে প্রবাহিত হচ্ছে",
    ],
)
def test_causes_that_could_be_the_event_need_a_cue(text):
    assert "cause" not in got(text)


@pytest.mark.parametrize(
    ("text", "status"),
    [
        ("Floodwater has receded", "resolved"),
        ("আগুন নিয়ন্ত্রণে এসেছে", "resolved"),
        ("pani ekhono barche", "worsening"),
        ("পানি কমতে শুরু করেছে", "improving"),
        ("Rescue work is still continuing", "ongoing"),
    ],
)
def test_status(text, status):
    assert got(text)["status"] == status


def test_moving_traffic_is_not_a_status():
    assert "status" not in got("Mirpur 10 e hatu pani, gari choltese na")


@pytest.mark.parametrize(
    "text",
    [
        "No blockade in Moulvibazar; the report going round is a rumour",
        "Reports of a building collapse in Tejgaon are false",
        "তেজগাঁওয়ে ভবন ধসের খবরটি গুজব",
        "kono agun lage nai, eta gujob",
    ],
)
def test_denials(text):
    assert got(text)["occurrence"] is False


def test_no_casualties_is_not_a_denial():
    assert "occurrence" not in got("Fire at Kawran Bazar; no casualties")


def test_claims_are_dataset_claims():
    claims = extract("Massive fire: 4 people killed, cause: electrical short circuit. " * 10)
    for c in claims:
        d = c.as_dict()
        assert set(d) <= {"attribute", "value", "unit", "surface"}
        assert len(d.get("surface", "")) <= 200
    assert len({c.attribute for c in claims}) == len(claims)  # one per attribute


def test_largest_count_wins():
    assert got("3 killed on Monday; death toll rises to 7")["casualty_count"] == 7


# --- Evaluation ----------------------------------------------------------------------------


def test_agreement_follows_the_guideline():
    assert agrees("affected_count", 100, 119)
    assert not agrees("affected_count", 100, 130)
    assert agrees("casualty_count", 0, 0)
    assert agrees("magnitude", "Knee-deep", "knee-deep")


def test_development_examples_still_pass():
    """A guard against regressions; these examples were written with the rules."""
    r = score(dev_examples())
    assert r["macro_precision"] >= 0.95 and r["macro_f1"] >= 0.95
    assert r["language_accuracy"] >= 0.95


def test_held_out_examples_do_not_regress():
    r = score(dev_examples("held_out"))
    assert r["macro_precision"] >= 0.95 and r["macro_f1"] >= 0.85


def test_cli_on_a_dataset(tmp_path, capsys):
    rows = [
        {"obs_id": "OBS-1", "language": "en", "text": "3 people killed in the fire",
         "claims": [{"attribute": "casualty_count", "value": 3}]},
        {"obs_id": "OBS-2", "language": "bn", "text": "হাঁটুসমান পানি",
         "claims": [{"attribute": "magnitude", "value": "waist-deep"}]},
        {"obs_id": "OBS-3", "language": "en", "content_policy": "reference_only"},
    ]  # fmt: skip
    (tmp_path / "observations.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    out = tmp_path / "r.json"
    assert main([str(tmp_path), "--misses", "5", "--json", str(out)]) == 0
    r = json.loads(out.read_text())
    assert r["examples"] == 2
    assert r["attributes"]["casualty_count"]["f1"] == 1.0
    assert r["attributes"]["magnitude"]["precision"] == 0.0
    assert "labelled 'waist-deep', extracted 'knee-deep'" in capsys.readouterr().out
    assert main([str(tmp_path / "missing")]) == 1


def test_precomposed_bangla_letters_read_the_same():
    """য়, ড় can be one code point or a letter plus nukta; both must work."""
    decomposed = "টানা বৃষ্টিতে হাঁটুসমান পানি, ছয়জন নিহত"
    precomposed = decomposed.replace("\u09af\u09bc", "\u09df").replace("\u09a1\u09bc", "\u09dc")
    assert precomposed != decomposed
    assert got(precomposed) == got(decomposed) == {
        "magnitude": "knee-deep", "cause": "heavy rain", "casualty_count": 6
    }  # fmt: skip
    assert detect_language(precomposed) == "bn"
