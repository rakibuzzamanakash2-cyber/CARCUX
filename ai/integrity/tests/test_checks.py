from datetime import datetime, timedelta, timezone

from carcux_integrity.checks import (
    Report,
    Text,
    burst,
    check,
    copied_text,
    location_text_mismatch,
    photos,
    similarity,
    timing,
    travel,
)

DHAKA = timezone(timedelta(hours=6))
T0 = datetime(2026, 7, 10, 12, 0, tzinfo=DHAKA)
MIRPUR = (23.807, 90.368)
SYLHET = (24.8898, 91.8698)


def rep(rid="R1", account="W1", text="pani", at=T0, where=MIRPUR, acc=30.0, photos=()):
    return Report(rid, account, text, where[0], where[1], at, at, acc, tuple(photos))


def codes(flags):
    return [f.code for f in flags]


def test_timing():
    assert codes(timing(rep(at=T0 + timedelta(hours=1)), T0)) == ["observed_in_future"]
    assert codes(timing(rep(at=T0 - timedelta(hours=30)), T0)) == ["old_observation"]
    assert timing(rep(), T0) == []


def test_travel_between_far_places_in_minutes():
    earlier = rep("R0", at=T0 - timedelta(minutes=20))
    now = rep("R1", where=SYLHET)
    assert codes(travel(now, [earlier])) == ["impossible_travel"]
    # Hours later the same trip is possible; another account's report never counts.
    assert travel(rep("R1", where=SYLHET, at=T0 + timedelta(hours=5)), [earlier]) == []
    assert travel(now, [rep("R0", account="W2", at=T0 - timedelta(minutes=20))]) == []


def test_burst_counts_the_same_account_only():
    history = [rep(f"R{i}", at=T0 - timedelta(seconds=30 * i)) for i in range(1, 11)]
    assert codes(burst(rep("R99"), history)) == ["submission_burst"]
    assert burst(rep("R99"), history[:9]) == []
    assert burst(rep("R99", account="W2"), history) == []


def test_photo_reused_within_a_few_bits():
    old = rep("R0", photos=["ffffffffffffffff"])
    assert codes(photos(rep("R1", photos=["fffffffffffffff0"]), [old])) == ["photo_reused"]
    assert photos(rep("R1", photos=["0000000000000000"]), [old]) == []


def test_location_text_mismatch_far_from_named_place():
    f = location_text_mismatch(rep(text="Sylhet e pani uthse", where=MIRPUR))
    assert codes(f) == ["location_text_mismatch"]
    assert "Sylhet" in f[0].detail


def test_location_text_mismatch_near_or_unnamed():
    assert location_text_mismatch(rep(text="Mirpur 10 e hatu pani", where=MIRPUR)) == []
    assert location_text_mismatch(rep(text="pani komse", where=MIRPUR)) == []
    # Near one of two named places is enough.
    assert location_text_mismatch(rep(text="Sylhet theke Mirpur e aslam", where=MIRPUR)) == []


def test_location_text_mismatch_allows_for_poor_gps():
    # 20 km of GPS uncertainty covers a report about a district centre 25 km away.
    near = (MIRPUR[0], MIRPUR[1] + 0.25)  # about 25 km east
    assert codes(location_text_mismatch(rep(text="Mirpur 10 e pani", where=near))) == [
        "location_text_mismatch"
    ]
    assert location_text_mismatch(rep(text="Mirpur 10 e pani", where=near, acc=20000)) == []


RUMOUR = "Breaking: dam gates opened upstream, everyone in the district must leave tonight"


def test_similarity():
    assert similarity("abc def", "ABC, def!") == 1.0
    assert similarity("pani jomeche", "current nai") < 0.2


def test_copied_from_public_post():
    f = copied_text(rep(text=RUMOUR + "!!"), [Text("P1", RUMOUR, "public post")])
    assert codes(f) == ["copied_text"] and "public post P1" in f[0].detail


def test_short_texts_are_not_compared():
    assert (
        copied_text(rep(text="Mirpur e pani"), [Text("P1", "Mirpur e pani", "public post")]) == []
    )


def test_two_workers_writing_alike_is_not_copying():
    # Medium length, near-identical, from another worker: corroboration, not a copy.
    t = "Mirpur 10 e pani jomeche, rasta diye hata jacche na"
    assert copied_text(rep(text=t), [Text("R0", t, "report", "W2")]) == []
    # Long and identical from another account is flagged; one's own earlier report is not.
    assert codes(
        copied_text(
            rep(text=RUMOUR + " " + RUMOUR), [Text("R0", RUMOUR + " " + RUMOUR, "report", "W2")]
        )
    ) == ["copied_text"]
    assert (
        copied_text(
            rep(text=RUMOUR + " " + RUMOUR), [Text("R0", RUMOUR + " " + RUMOUR, "report", "W1")]
        )
        == []
    )


def test_check_runs_everything_and_ordinary_report_is_clean():
    assert check(rep(text="Mirpur 10 e hatu pani"), [rep("R0", at=T0 - timedelta(hours=2))]) == []
    f = check(rep(text="Sylhet e pani", acc=1500), [], [], now=T0 + timedelta(hours=2))
    assert set(codes(f)) == {"location_text_mismatch", "poor_location_accuracy"}
