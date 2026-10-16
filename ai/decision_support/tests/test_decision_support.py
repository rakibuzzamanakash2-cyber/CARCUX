"""Decision support: priority from operational factors, summaries whose every sentence
cites evidence, and what changed."""

from datetime import UTC, datetime, timedelta

import pytest

from carcux_decision_support import (
    Detail,
    Estimate,
    EventFacts,
    Evidence,
    LogEntry,
    suggest,
    summarise,
    what_changed,
)

T0 = datetime(2024, 8, 21, 6, 0, tzinfo=UTC)
H = timedelta(hours=1)


def deaths(n):
    return (Detail("casualty_count", n, "deaths", f"{n} dead"),)


def ev(i, source, relation="supports", hours=0, details=(), reliability=0.7, **kw):
    return Evidence(f"E{i}", source, kw.pop("kind", "news"), relation, T0 + hours * H,
                    details=details, reliability=reliability, **kw)  # fmt: skip


def flood(**kw) -> EventFacts:
    """Eastern flash flood: the toll rose over days, one outlet blamed the dam."""
    base = dict(
        id="N07", title="Eastern flash flood", event_type="flash_flood",
        family="natural_calamity", place_name="Feni", started_at=T0 - 30 * H, ended_at=None,
        status="active", assessment="verified", suggested="verified", probability=0.97,
        estimates=[Estimate("casualty_count", 71, "deaths", False),
                   Estimate("affected_count", 5_400_000, "people", False)],
        evidence=[
            ev(1, "BBC Bangla", headline="ভারত থেকে ঢুকছে পানি"),
            ev(2, "Daily Star", hours=50, details=deaths(23)),
            ev(3, "Prothom Alo", hours=120, details=deaths(52)),
            ev(4, "bdnews24", hours=146,
               details=(*deaths(54), Detail("affected_count", 5_400_000, "people"))),
            ev(5, "bdnews24", hours=290, details=deaths(71), headline="Death toll hits 71"),
            ev(6, "Daily Star", hours=289, details=deaths(71)),
            ev(7, "A field worker", hours=10, kind="field", reliability=0.8),
            ev(8, "Some page", relation="related", hours=20, kind="social", reliability=0.3),
            ev(9, "Copy site", hours=291, details=deaths(71), copy_of="E5", reliability=0.2),
        ],
    )  # fmt: skip
    return EventFacts(**(base | kw))


def test_a_deadly_spreading_flood_is_critical_and_says_why():
    now = T0 + 292 * H
    p = suggest(flood(), now)
    assert p.level == "critical"
    names = {f.name for f in p.factors}
    assert {"hazard", "deaths", "affected", "duration"} <= names
    assert any("About 71 dead" in f.reason for f in p.factors)
    assert p.score == sum(f.points for f in p.factors)


@pytest.mark.parametrize(
    ("changes", "level"),
    [
        ({"status": "resolved"}, "low"),
        ({"status": "dismissed"}, "low"),
        ({"suggested": "refuted", "estimates": []}, "low"),
    ],
)
def test_over_dismissed_or_refuted_is_low(changes, level):
    assert suggest(flood(**changes), T0 + 292 * H).level == level


def test_a_small_waterlogging_with_one_report_is_low():
    e = flood(event_type="waterlogging", estimates=[], evidence=[ev(1, "A field worker")])
    p = suggest(e, T0 + 2 * H)
    assert p.level == "low"
    assert any(f.name == "confidence" and f.points == -1 for f in p.factors)


def test_a_fast_growing_fire_is_critical():
    fire = EventFacts(
        id="U01", title="Bailey Road fire", event_type="fire", family="urban_emergency",
        place_name="Bailey Road", started_at=T0, ended_at=None, status="active",
        assessment="unverified", estimates=[Estimate("casualty_count", 44, "deaths", False)],
        evidence=[ev(i, f"Outlet {i}", hours=1 + i * 0.2, details=deaths(43 + i % 3))
                  for i in range(1, 5)],
    )  # fmt: skip
    p = suggest(fire, T0 + 2 * H)
    assert p.level == "critical" and any(f.name == "growing" for f in p.factors)


def test_priority_never_reads_who_is_involved():
    # Swapping every source name changes nothing.
    a = suggest(flood(), T0 + 292 * H)
    renamed = flood(evidence=[Evidence(**{**e.__dict__, "source": f"S{k}"})
                              for k, e in enumerate(flood().evidence)])  # fmt: skip
    b = suggest(renamed, T0 + 292 * H)
    assert (a.level, a.score) == (b.level, b.score)


# --- Summaries ------------------------------------------------------------------------


def test_every_sentence_cites_evidence_that_exists():
    s = summarise(flood())
    ids = {e.id for e in flood().evidence}
    assert s and all(x.cites for x in s)
    assert all(set(x.cites) <= ids for x in s)


def test_the_summary_follows_a_rising_toll_and_counts_copies_once():
    text = [x.text for x in summarise(flood())]
    deaths_line = next(t for t in text if t.startswith("Deaths:"))
    assert "71 dead, as Daily Star and bdnews24 say" in deaths_line
    assert "Earlier reports gave 23, 52, 54 as the figure rose" in deaths_line
    assert any(t.startswith("1 item repeats an earlier one") for t in text)
    assert text[0].startswith("Flash flood at Feni, since")
    assert any(t.startswith("Latest: Copy site") or t.startswith("Latest: bdnews24")
               for t in text)  # fmt: skip


def test_a_disputed_detail_names_both_sides_and_denials_are_quoted():
    e = flood(
        estimates=[Estimate("cause", "upstream runoff", None, True)],
        evidence=[
            ev(1, "Outlet A", details=(Detail("cause", "upstream runoff"),)),
            ev(2, "Outlet B", hours=1, details=(Detail("cause", "heavy rain"),)),
            ev(3, "Ministry", relation="contradicts", hours=2, denial="বাঁধ খুলে দেওয়া হয়নি"),
        ],
    )
    s = summarise(e)
    disputed = next(x for x in s if x.kind == "disputed")
    assert "Cause is disputed" in disputed.text and set(disputed.cites) == {"E1", "E2"}
    denial = next(x for x in s if x.kind == "denial")
    assert denial.text == "Ministry calls it false: “বাঁধ খুলে দেওয়া হয়নি”." and denial.cites == ["E3"]
    assert "2 sources say it happened (2 credible); 1 says it did not" in s[1].text


def test_no_evidence_says_so_instead_of_guessing():
    (only,) = summarise(flood(evidence=[]))
    assert "No evidence is linked yet" in only.text and only.cites == []


# --- What changed ---------------------------------------------------------------------


def test_what_changed_since_yesterday():
    since, now = T0 + 270 * H, T0 + 292 * H
    log = [LogEntry(T0 + 280 * H, "Priority set to critical."), LogEntry(T0, "Created.")]
    out = what_changed(flood(), since, now, log)
    assert out[0].text == "2 new items: 2 support it." and set(out[0].cites) == {"E5", "E6"}
    count = next(x for x in out if x.kind == "count")
    assert "now says 71, up from 54" in count.text
    assert [x.text.split(": ", 1)[1] for x in out if x.kind == "decision"] == [
        "Priority set to critical."
    ]


def test_nothing_new():
    out = what_changed(flood(), T0 + 400 * H, T0 + 401 * H)
    assert len(out) == 1 and out[0].text.startswith("Nothing new since")


def test_two_figures_said_at_the_same_moment_do_not_break_what_changed():
    # Two outlets give the same toll at the same minute: ordering must not compare items.
    e = flood(evidence=[ev(1, "A", hours=1, details=deaths(23)),
                        ev(2, "B", hours=5, details=deaths(52)),
                        ev(3, "C", hours=5, details=deaths(52))])  # fmt: skip
    out = what_changed(e, T0 + 2 * H, T0 + 6 * H)
    assert any("up from 23" in x.text for x in out)


def test_field_workers_are_counted_apart_though_never_named():
    fw = dict(kind="field", reliability=0.8)
    e = flood(
        estimates=[Estimate("casualty_count", 3, "deaths", True)],
        evidence=[
            ev(1, "A field worker", details=deaths(3), source_key="reporter:1", **fw),
            ev(2, "A field worker", hours=1, details=deaths(20), source_key="reporter:2", **fw),
            ev(3, "A field worker", relation="contradicts", hours=2, source_key="reporter:3", **fw),
        ],
    )
    s = summarise(e)
    assert "2 sources say it happened (2 credible); 1 says it did not" in s[1].text
    # Two field workers disagreeing on deaths is a dispute between two sources.
    assert any(x.kind == "disputed" for x in s)
    assert suggest(e, T0 + 3 * H).factors[-1].reason != "Only one source so far."
    agree = flood(
        estimates=[Estimate("casualty_count", 3, "deaths", False)],
        evidence=[ev(i, "A field worker", hours=i, details=deaths(3), source_key=f"r{i}", **fw)
                  for i in (1, 2)],
    )  # fmt: skip
    line = next(x.text for x in summarise(agree) if x.kind == "detail")
    assert "as 2 field workers say" in line
