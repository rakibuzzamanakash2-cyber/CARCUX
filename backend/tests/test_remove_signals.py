"""remove-signals: lists first, dismisses or deletes on request, never removes evidence."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app import cli
from app.core.config import get_settings
from app.core.event_types import EVENT_TYPE_FAMILY
from app.models.audit import AuditLog
from app.models.event import Event, EventEvidence, EvidenceRelation
from app.models.signal import Adapter, Signal, SignalStatus, Source, SourceType
from app.models.user import Role
from app.services.audit import AuditAction
from tests.conftest import TEST_DATABASE_URL

NOW = datetime(2026, 11, 6, 6, tzinfo=UTC)


def _run(monkeypatch, *args):
    monkeypatch.setenv("CARCUX_DATABASE_URL", TEST_DATABASE_URL)
    get_settings.cache_clear()
    try:
        return cli.main(["remove-signals", *args])
    finally:
        get_settings.cache_clear()


def _setup(db, make_user):
    analyst = make_user("analyst@office.local", Role.ANALYST)
    src = Source(id=uuid.uuid4(), key="test-feed", name="Test feed",
                 source_type=SourceType.NEWS, adapter=Adapter.RSS)  # fmt: skip
    db.add(src)
    db.flush()

    def signal(title, by_hand=False, days=0):
        s = Signal(id=uuid.uuid4(), source_id=src.id, external_id=str(uuid.uuid4()),
                   title=title, published_at=NOW - timedelta(days=days), content_hash="0" * 64,
                   entered_by_id=analyst.id if by_hand else None)  # fmt: skip
        db.add(s)
        db.flush()
        return s

    test1 = signal("TEST flood at Mirpur", by_hand=True)
    test2 = signal("TEST fire at Gulshan", by_hand=True)
    feed = signal("Flood in Sylhet", days=3)
    used = signal("TEST waterlogging at Mirpur 10", by_hand=True)
    event = Event(id=uuid.uuid4(), title="Waterlogging", event_type="waterlogging",
                  family=EVENT_TYPE_FAMILY["waterlogging"], latitude=23.8, longitude=90.4,
                  started_at=NOW, created_by_id=analyst.id)  # fmt: skip
    db.add(event)
    db.flush()
    link = EventEvidence(id=uuid.uuid4(), event_id=event.id, signal_id=used.id,
                         relation=EvidenceRelation.SUPPORTS, linked_by_id=analyst.id)  # fmt: skip
    db.add(link)
    db.commit()
    return test1, test2, feed, used


def test_nothing_changes_without_an_action(monkeypatch, engine, db, make_user, capsys):
    _setup(db, make_user)
    assert _run(monkeypatch, "--by-hand") == 0
    out = capsys.readouterr().out
    assert "3 match; 1 are evidence" in out and "Nothing changed" in out
    db.expire_all()
    assert all(s.status == SignalStatus.NEW for s in db.scalars(select(Signal)))


def test_a_filter_is_required(monkeypatch, engine, db, make_user):
    _setup(db, make_user)
    assert _run(monkeypatch, "--delete") == 2
    assert len(db.scalars(select(Signal)).all()) == 4


def test_delete_keeps_evidence_and_is_audited(monkeypatch, engine, db, make_user):
    test1, test2, feed, used = _setup(db, make_user)
    assert _run(monkeypatch, "--title", "test", "--delete") == 0
    db.expire_all()
    left = {s.id for s in db.scalars(select(Signal))}
    assert left == {feed.id, used.id}
    entry = db.scalar(select(AuditLog).where(AuditLog.action == AuditAction.SIGNALS_REMOVED))
    assert entry.details["how"] == "deleted" and entry.details["count"] == 2


def test_dismiss_hides_without_deleting(monkeypatch, engine, db, make_user):
    test1, test2, feed, used = _setup(db, make_user)
    assert _run(monkeypatch, "--source", "test-feed", "--before", "2026-11-05", "--dismiss") == 0
    db.expire_all()
    assert db.get(Signal, feed.id).status == SignalStatus.DISMISSED
    assert db.get(Signal, test1.id).status == SignalStatus.NEW
    assert len(db.scalars(select(Signal)).all()) == 4
