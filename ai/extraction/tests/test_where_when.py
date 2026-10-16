"""Places and times named in Bangla, Banglish and English text."""

from datetime import datetime, timedelta, timezone

import pytest

from carcux_extraction import evaluate_where_when as ww
from carcux_extraction.places import best_place, find_places
from carcux_extraction.times import observed_at, times

DHAKA = timezone(timedelta(hours=6))
PUB = datetime(2024, 3, 1, 1, 52, tzinfo=DHAKA)


def names(text):
    return [(p.name, p.district) for p in find_places(text)]


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("Mirpure agun", [("Mirpur", "Dhaka")]),
        ("Mirpur-e pani", [("Mirpur", "Dhaka")]),
        ("Dhakay bristi", [("Dhaka", "Dhaka")]),
        ("Old Dhaka's Lalbagh", [("Old Dhaka", "Dhaka"), ("Lalbagh", "Dhaka")]),
        ("মিরপুরে ভবন হেলে পড়েছে", [("Mirpur", "Dhaka")]),
        ("Mirpur 10 golchottor", [("Mirpur", "Dhaka")]),  # the longest name wins
        ("Chittagong port", [("Chattogram", "Chattogram")]),
    ],
)
def test_names_as_people_write_them(text, want):
    assert names(text) == want


def test_the_text_settles_an_ambiguous_name():
    # Mirpur is a Dhaka locality and an upazila of Kushtia.
    assert names("Mirpur e pani") == [("Mirpur", "Dhaka")]
    assert ("Mirpur", "Kushtia") in names("Kushtia-r Mirpur upazilay bonna")
    # Lohagara is an upazila of both Chattogram and Narail.
    assert ("Lohagara", "Narail") in names("Lohagara, Narail")
    assert ("Lohagara", "Chattogram") in names("Chattogram er Lohagara te")


def test_no_place_in_ordinary_words():
    assert names("The rate may rise; water everywhere") == []


def test_best_place_is_specific_and_widens_for_several_districts():
    p = best_place("Fire in Mirpur, Dhaka")
    assert (p.name, p.level, p.precision_m) == ("Mirpur", "locality", 2_500)
    wide = best_place("Flood in Feni and Noakhali")
    assert wide.name == "Feni" and wide.precision_m > 30_000


def at(text, pub=PUB):
    return [(t.start.strftime("%Y-%m-%d %H:%M"), t.precision) for t in times(text, pub)]


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("The fire broke out at 9:50pm on 29 February", [("2024-02-29 21:50", "minute")]),
        ("Gotokal raat 10 tay agun lage", [("2024-02-29 22:00", "minute")]),
        ("গতকাল রাত ১০টায় আগুন লাগে", [("2024-02-29 22:00", "minute")]),
        ("আজ সকালে পানি", [("2024-03-01 06:00", "part_of_day")]),
        ("Last night a fire broke out", [("2024-02-29 20:00", "part_of_day")]),
        ("২১ নভেম্বর সকাল ১০টা ৩৮ মিনিটে", [("2023-11-21 10:38", "minute")]),
        ("at 11 pm", [("2024-02-29 23:00", "minute")]),  # said after midnight
    ],
)
def test_times_made_absolute(text, want):
    assert at(text) == want


def test_unclear_words_are_left_out():
    # "kal" alone is yesterday or tomorrow; a bare part of the day has no day.
    assert at("kal theke pani barche") == []
    assert at("The death rate may rise") == []


def test_last_night_runs_into_the_small_hours():
    (t,) = times("last night", PUB)
    assert t.end - t.start == timedelta(hours=10)


def test_observed_at_is_the_earliest_time_not_after_publication():
    text = "Fire started at 9:50 pm on 29 February; by 1 am on 1 March it was out"
    assert observed_at(text, PUB) == datetime(2024, 2, 29, 21, 50, tzinfo=DHAKA)
    assert observed_at("no time here", PUB) is None


def test_the_labelled_examples_score_as_reported():
    dev = ww.score(ww.examples("where_when_dev"))
    assert dev["places"]["f1"] == 1.0 and dev["times"]["f1"] == 1.0
    held = ww.score(ww.examples("where_when_held_out"))
    assert held["places"]["precision"] == 1.0 and held["times"]["precision"] == 1.0
