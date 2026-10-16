"""An event without an end time matches items up to a week after its latest linked item
(or its start), never past now: old case studies do not pull in news from years later,
live events keep moving forward."""

import uuid
from datetime import UTC, datetime, timedelta

from app.models.event import EventEvidence, EvidenceRelation
from app.models.signal import Signal
from app.services import events as service
from tests.test_assessment import _event, _feed
from tests.test_assessment import people as people  # noqa: F401 (fixture)

NOW = datetime.now(UTC)


def _signal(db, source, when, title="Flood at Mirpur 10") -> Signal:
    s = Signal(
        id=uuid.uuid4(), source_id=source.id, external_id=str(uuid.uuid4()), title=title,
        published_at=when, content_hash="0" * 64, latitude=23.8069, longitude=90.3687,
    )  # fmt: skip
    db.add(s)
    db.flush()
    return s


def _link(db, event, signal, analyst, relation=EvidenceRelation.SUPPORTS):
    db.add(
        EventEvidence(
            id=uuid.uuid4(),
            event_id=event.id,
            signal_id=signal.id,
            relation=relation,
            linked_by_id=analyst.id,
        )  # fmt: skip
    )
    db.flush()


def _offered(db, event) -> set[uuid.UUID]:
    return {s.id for s, _ in service.candidate_signals(db, event)}


def test_an_old_open_event_is_not_offered_news_from_long_after(db, people):
    old = _event(db, people["analyst"], hours=24 * 400)  # started 400 days ago, no end
    src = _feed(db)
    at_the_time = _signal(db, src, old.started_at + timedelta(days=2))
    this_month = _signal(db, src, NOW - timedelta(days=3))
    assert _offered(db, old) == {at_the_time.id}
    # ...and the item is not offered that event either.
    assert old.id not in {e.id for e, _ in service.candidate_events_for_signal(db, this_month)}
    assert old.id in {e.id for e, _ in service.candidate_events_for_signal(db, at_the_time)}


def test_linked_items_carry_the_window_forward(db, people):
    a = people["analyst"]
    old = _event(db, a, hours=24 * 60)
    src = _feed(db)
    week_two = _signal(db, src, old.started_at + timedelta(days=12))
    assert week_two.id not in _offered(db, old)  # beyond a week (+48 h) after the start
    _link(db, old, _signal(db, src, old.started_at + timedelta(days=6)), a)
    assert week_two.id in _offered(db, old)  # within a week of the latest linked item


def test_items_labelled_not_this_event_do_not_extend_it(db, people):
    a = people["analyst"]
    old = _event(db, a, hours=24 * 300)
    src = _feed(db)
    _link(db, old, _signal(db, src, NOW - timedelta(days=1), "Gazipur factory fire"), a,
          EvidenceRelation.UNRELATED)  # fmt: skip
    recent = _signal(db, src, NOW - timedelta(days=2))
    assert recent.id not in _offered(db, old)


def test_a_live_event_and_an_explicit_end(db, people):
    a = people["analyst"]
    live = _event(db, a)  # started 6 h ago
    src = _feed(db)
    fresh = _signal(db, src, NOW - timedelta(hours=1))
    assert fresh.id in _offered(db, live)
    ended = _event(db, a, hours=24 * 400)
    ended.ended_at = ended.started_at + timedelta(days=30)
    late_but_in = _signal(db, src, ended.started_at + timedelta(days=25))
    assert late_but_in.id in _offered(db, ended)  # an end time set by an analyst wins
    assert service.effective_end(ended, NOW) == ended.ended_at
