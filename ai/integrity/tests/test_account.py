from datetime import datetime, timedelta, timezone

from carcux_integrity.account import score
from carcux_integrity.checks import Flag, Report

DHAKA = timezone(timedelta(hours=6))
START = datetime(2026, 7, 1, tzinfo=DHAKA)
NOW = START + timedelta(days=15)
MIRPUR = (23.807, 90.368)
SYLHET = (24.8898, 91.8698)


def history(account="W1", days=14, per_day=3, where=MIRPUR):
    out = []
    for d in range(days):
        for k in range(per_day):
            at = START + timedelta(days=d, hours=10 + 3 * k)
            lat = where[0] + 0.005 * ((d + k) % 3 - 1)
            out.append(Report(f"{account}-{d}-{k}", account, "pani", lat, where[1], at, at, 30))
    return out


def recent(account="W1", n=3, where=MIRPUR, hour=12, gap=timedelta(hours=1), start=None):
    t = start or (NOW - timedelta(days=1) + timedelta(hours=hour - 0))
    return [
        Report(
            f"{account}-new-{i}", account, "pani", where[0], where[1], t + i * gap, t + i * gap, 30
        )
        for i in range(n)
    ]


def test_as_usual_scores_low():
    reports = history() + recent(hour=10, gap=timedelta(hours=3))
    r = score("W1", reports, {}, NOW)
    assert r.score < 0.2 and r.reasons == []
    assert r.recent == 3 and r.baseline == 42


def test_far_from_usual_area():
    r = score("W1", history() + recent(where=SYLHET, hour=8), {}, NOW)
    assert r.score >= 0.8
    assert any("km from where it usually reports" in x for x in r.reasons)


def test_many_more_reports_than_usual():
    many = recent(n=30, hour=6, gap=timedelta(minutes=20))
    r = score("W1", history() + many, {}, NOW)
    assert r.parts["rate"] == 1.0
    assert any("30 reports in the last day; it usually sends about 3" in x for x in r.reasons)


def test_unusual_hours():
    night = recent(n=4, start=NOW - timedelta(hours=20), gap=timedelta(minutes=20))  # ~4 am
    r = score("W1", history() + night, {}, NOW)
    assert r.parts["hours"] == 1.0 and r.score >= 0.5


def test_flags_raise_the_score_and_are_named():
    new = recent(hour=10, gap=timedelta(hours=3))
    flags = {x.id: [Flag("copied_text", "")] for x in new[:2]}
    r = score("W1", history() + new, flags, NOW)
    assert r.score >= 0.5
    assert any("copied_text" in x for x in r.reasons)


def test_new_account_is_judged_by_flags_only():
    r = score("W9", recent("W9", where=SYLHET), {}, NOW)
    assert r.score == 0.0 and "Only 0 earlier reports" in r.reasons[0]


def test_no_recent_reports():
    r = score("W1", history(), {}, NOW)
    assert r.score == 0.0 and r.recent == 0


def test_other_accounts_do_not_matter():
    r = score(
        "W1",
        history()
        + history("W2")
        + recent("W2", where=SYLHET, hour=8)
        + recent(hour=10, gap=timedelta(hours=3)),
        {},
        NOW,
    )
    assert r.score < 0.2
