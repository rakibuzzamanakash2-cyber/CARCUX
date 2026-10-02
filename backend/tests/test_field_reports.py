import io
import json
import uuid
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select, text

from app.core.event_types import EVENT_TYPES
from app.main import create_app
from app.models.audit import AuditLog
from app.models.field_report import FieldReport
from app.models.user import Role
from app.services.audit import AuditAction
from app.services.field_reports import ReportInput, content_hash
from app.services.media import InvalidMediaError, resolve

URL = "/api/v1/field-reports"
DHAKA = timezone(timedelta(hours=6))
MIRPUR = (23.8069, 90.3687)


def photo(seed: int = 1, size=(320, 240), fmt="PNG") -> bytes:
    """A photo-like test image: sky-to-ground gradient plus a few blocks.

    Broad shapes, like real photos, so perceptual hashing behaves realistically
    (high-frequency synthetic patterns alias badly when resized).
    """
    import random

    from PIL import ImageDraw

    rnd = random.Random(seed)  # noqa: S311 (test data, not crypto)
    w, h = size
    img = Image.new("RGB", size)
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        draw.line([(0, y), (w, y)], fill=(int(90 + 120 * t), int(140 + 60 * t), int(200 - 120 * t)))
    for _ in range(6):
        x0, y0 = rnd.randrange(w), rnd.randrange(h)
        x1, y1 = x0 + rnd.randrange(w // 10, w // 2), y0 + rnd.randrange(h // 12, h // 2)
        draw.rectangle([x0, y0, x1, y1], fill=tuple(rnd.randrange(256) for _ in range(3)))
    buf = io.BytesIO()
    img.save(buf, fmt)
    return buf.getvalue()


def noisy_photo(size=(400, 400)) -> bytes:
    """Random noise does not compress, so its file size is predictable (~3 bytes/pixel)."""
    import random

    noise = random.Random(42).randbytes(size[0] * size[1] * 3)  # noqa: S311 (test data, not crypto)
    img = Image.frombytes("RGB", size, noise)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def form(**overrides) -> dict:
    data = {
        "client_report_id": str(uuid.uuid4()),
        "text": "Mirpur 10 golchottor e hatu pani, bus cholche na.",
        "latitude": MIRPUR[0],
        "longitude": MIRPUR[1],
        "location_accuracy_m": 15,
        "observed_at": datetime.now(DHAKA).isoformat(),
        "event_type": "waterlogging",
        "place_name": "Mirpur 10 golchottor",
    }
    data.update(overrides)
    return {k: str(v) for k, v in data.items() if v is not None}


def submit(client, headers, photos=(), **overrides):
    files = [("photos", (f"p{i}.png", data, "image/png")) for i, data in enumerate(photos)]
    return client.post(URL, data=form(**overrides), files=files or None, headers=headers)


@pytest.fixture
def worker(make_user, login):
    make_user("worker@office.local", Role.FIELD_WORKER)
    return login("worker@office.local")


@pytest.fixture
def worker2(make_user, login):
    make_user("worker2@office.local", Role.FIELD_WORKER)
    return login("worker2@office.local")


@pytest.fixture
def analyst(make_user, login):
    make_user("analyst@office.local", Role.ANALYST)
    return login("analyst@office.local")


# --- Submitting ------------------------------------------------------------------------


def test_field_worker_submits_report_with_photo(client, worker, db):
    response = submit(client, worker, photos=[photo(1)])

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "submitted"
    assert len(body["content_hash"]) == 64
    assert body["integrity_flags"] == []
    assert len(body["media"]) == 1
    assert body["media"][0]["content_type"] == "image/png"
    assert body["reporter"]["full_name"] == "Test User"

    entry = db.scalar(select(AuditLog).where(AuditLog.action == AuditAction.FIELD_REPORT_SUBMITTED))
    assert entry.target_id == body["id"]
    assert entry.details["photos"] == 1


def test_retry_with_same_client_id_returns_the_same_report(client, worker, db):
    fields = form()
    first = client.post(
        URL, data=fields, files=[("photos", ("a.png", photo(1), "image/png"))], headers=worker
    )
    again = client.post(
        URL, data=fields, files=[("photos", ("a.png", photo(1), "image/png"))], headers=worker
    )

    assert first.status_code == 201
    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]
    assert db.scalar(select(text("count(*)")).select_from(FieldReport)) == 1


def test_reusing_client_id_for_different_content_is_rejected(client, worker):
    cid = str(uuid.uuid4())
    assert submit(client, worker, client_report_id=cid).status_code == 201
    response = submit(client, worker, client_report_id=cid, text="Something else entirely")
    assert response.status_code == 409


@pytest.mark.parametrize("role", [Role.ANALYST, Role.VIEWER])
def test_only_field_workers_and_admins_can_submit(client, make_user, login, role):
    make_user("someone@office.local", role)
    assert submit(client, login("someone@office.local")).status_code == 403


def test_admin_can_submit(client, admin_headers):
    assert submit(client, admin_headers).status_code == 201


def test_submitting_requires_sign_in(client):
    assert client.post(URL, data=form()).status_code == 401


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"latitude": 30.0}, "latitude"),
        ({"longitude": 80.0}, "longitude"),
        ({"observed_at": "2026-07-14T08:45:00"}, "UTC offset"),
        ({"event_type": "political_rally"}, "Unknown event_type"),
        ({"text": ""}, "text"),
    ],
)
def test_invalid_fields_are_rejected(client, worker, overrides, message):
    response = submit(client, worker, **overrides)
    assert response.status_code == 422
    assert message in response.text


def test_too_many_photos(client, worker):
    response = submit(client, worker, photos=[photo(i) for i in range(1, 6)])
    assert response.status_code == 422
    assert "At most 4 photos" in response.text


def test_non_image_with_image_name_is_rejected(client, worker):
    files = [("photos", ("holiday.jpg", b"MZ\x90\x00 definitely not a jpeg", "image/jpeg"))]
    response = client.post(URL, data=form(), files=files, headers=worker)
    assert response.status_code == 422
    assert "not a valid image" in response.text


def test_unsupported_image_format_is_rejected(client, worker):
    response = submit(client, worker, photos=[photo(1, fmt="GIF")])
    assert response.status_code == 422
    assert "JPEG, PNG or WebP" in response.text


def test_oversized_photo_is_rejected(engine, settings, make_user, login):
    small = settings.model_copy(update={"max_photo_bytes": 10_000})
    with TestClient(create_app(small)) as c:
        make_user("w@office.local", Role.FIELD_WORKER)
        headers = c.post(
            "/api/v1/auth/login",
            json={"email": "w@office.local", "password": "correct-horse-battery-staple"},
        ).json()
        response = submit(
            c,
            {"Authorization": f"Bearer {headers['access_token']}"},
            photos=[noisy_photo()],
        )
    assert response.status_code == 422
    assert "larger than" in response.text


# --- Who can see what ------------------------------------------------------------------


def test_field_workers_only_see_their_own_reports(client, worker, worker2):
    mine = submit(client, worker, photos=[photo(1)]).json()
    submit(client, worker2)

    listed = client.get(URL, headers=worker).json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == mine["id"]

    # Someone else's report is indistinguishable from a missing one.
    assert client.get(f"{URL}/{mine['id']}", headers=worker2).status_code == 404
    media_url = f"{URL}/{mine['id']}/media/{mine['media'][0]['id']}"
    assert client.get(media_url, headers=worker2).status_code == 404


def test_analysts_see_all_reports(client, worker, worker2, analyst):
    submit(client, worker)
    submit(client, worker2)
    assert client.get(URL, headers=analyst).json()["total"] == 2


def test_viewers_cannot_read_field_reports(client, make_user, login):
    make_user("viewer@office.local", Role.VIEWER)
    assert client.get(URL, headers=login("viewer@office.local")).status_code == 403


def test_unknown_report_is_404(client, analyst):
    assert client.get(f"{URL}/{uuid.uuid4()}", headers=analyst).status_code == 404


def test_photo_download(client, worker):
    data = photo(3)
    report = submit(client, worker, photos=[data]).json()
    response = client.get(f"{URL}/{report['id']}/media/{report['media'][0]['id']}", headers=worker)

    assert response.status_code == 200
    assert response.content == data
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "no-store" in response.headers["cache-control"]


def test_media_id_must_belong_to_the_report(client, worker):
    a = submit(client, worker, photos=[photo(1)]).json()
    b = submit(client, worker, photos=[photo(2)]).json()
    cross = f"{URL}/{a['id']}/media/{b['media'][0]['id']}"
    assert client.get(cross, headers=worker).status_code == 404


def test_storage_paths_cannot_escape_the_media_directory(tmp_path):
    with pytest.raises(InvalidMediaError):
        resolve(tmp_path, "../../etc/passwd")


def test_listing_filters_and_pages(client, worker, analyst):
    submit(client, worker)
    submit(client, worker, observed_at=(datetime.now(DHAKA) + timedelta(hours=2)).isoformat())

    assert client.get(URL, params={"flagged": "true"}, headers=analyst).json()["total"] == 1
    assert client.get(URL, params={"flagged": "false"}, headers=analyst).json()["total"] == 1
    page = client.get(URL, params={"limit": 1, "offset": 1}, headers=analyst).json()
    assert page["total"] == 2 and len(page["items"]) == 1


# --- Integrity flags -------------------------------------------------------------------


def flags_of(response) -> set[str]:
    return {f["code"] for f in response.json()["integrity_flags"]}


def test_reused_photo_is_flagged_even_across_reporters(client, worker, worker2):
    data = photo(5)
    submit(client, worker, photos=[data])
    assert "photo_reused" in flags_of(submit(client, worker2, photos=[data]))


def test_resized_copy_of_a_photo_is_flagged(client, worker, worker2):
    original = photo(7, size=(640, 480))
    resized = io.BytesIO()
    Image.open(io.BytesIO(original)).resize((320, 240)).save(resized, "JPEG", quality=80)
    submit(client, worker, photos=[original])
    response = submit(client, worker2, photos=[resized.getvalue()])
    assert "photo_reused" in flags_of(response)
    assert "near-identical" in response.text


def test_different_photos_are_not_flagged(client, worker, worker2):
    submit(client, worker, photos=[photo(1)])
    assert "photo_reused" not in flags_of(submit(client, worker2, photos=[photo(9)]))


def test_impossible_travel_is_flagged(client, worker):
    now = datetime.now(DHAKA)
    submit(client, worker, observed_at=now.isoformat())
    # Chattogram, ~210 km from Mirpur, 10 minutes later.
    response = submit(
        client,
        worker,
        latitude=22.3569,
        longitude=91.7832,
        observed_at=(now + timedelta(minutes=10)).isoformat(),
    )
    assert "impossible_travel" in flags_of(response)


def test_plausible_travel_is_not_flagged(client, worker):
    now = datetime.now(DHAKA)
    submit(client, worker, observed_at=(now - timedelta(hours=6)).isoformat())
    response = submit(
        client, worker, latitude=22.3569, longitude=91.7832, observed_at=now.isoformat()
    )
    assert "impossible_travel" not in flags_of(response)


def test_time_and_accuracy_flags(client, worker):
    now = datetime.now(DHAKA)
    assert "observed_in_future" in flags_of(
        submit(client, worker, observed_at=(now + timedelta(hours=1)).isoformat())
    )
    assert "old_observation" in flags_of(
        submit(client, worker, observed_at=(now - timedelta(days=2)).isoformat())
    )
    assert "poor_location_accuracy" in flags_of(submit(client, worker, location_accuracy_m=5000))


def test_submission_burst_is_flagged(client, worker):
    for _ in range(10):
        submit(client, worker)
    assert "submission_burst" in flags_of(submit(client, worker))


def test_flags_never_block_a_report(client, worker):
    response = submit(
        client, worker, observed_at=(datetime.now(DHAKA) + timedelta(days=1)).isoformat()
    )
    assert response.status_code == 201


# --- Tamper evidence -------------------------------------------------------------------


def test_untouched_report_verifies_as_intact(client, worker, analyst, db):
    report = submit(client, worker, photos=[photo(1), photo(2)]).json()
    result = client.get(f"{URL}/{report['id']}/verify", headers=analyst).json()

    assert result == {
        "report_id": report["id"],
        "intact": True,
        "problems": [],
        "content_hash": report["content_hash"],
    }
    entry = db.scalar(select(AuditLog).where(AuditLog.action == AuditAction.FIELD_REPORT_VERIFIED))
    assert entry.details["intact"] is True


def test_edited_database_row_is_detected(client, worker, analyst, engine):
    report = submit(client, worker).json()
    with engine.begin() as conn:  # someone with database access quietly edits the text
        conn.execute(
            text("UPDATE field_reports SET text = 'All clear, nothing happened' WHERE id = :id"),
            {"id": report["id"]},
        )
    result = client.get(f"{URL}/{report['id']}/verify", headers=analyst).json()
    assert result["intact"] is False
    assert "Report content has changed since submission." in result["problems"]


def test_moved_location_is_detected(client, worker, analyst, engine):
    report = submit(client, worker).json()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE field_reports SET latitude = 23.9 WHERE id = :id"), {"id": report["id"]}
        )
    assert client.get(f"{URL}/{report['id']}/verify", headers=analyst).json()["intact"] is False


def test_replaced_or_missing_photo_is_detected(client, worker, analyst, db, settings):
    report = submit(client, worker, photos=[photo(1), photo(2)]).json()
    row = db.get(FieldReport, uuid.UUID(report["id"]))
    first, second = (resolve(settings.media_dir, m.storage_key) for m in row.media)
    first.write_bytes(photo(99))
    second.unlink()

    result = client.get(f"{URL}/{report['id']}/verify", headers=analyst).json()
    assert result["intact"] is False
    assert "Photo 1 file has changed since submission." in result["problems"]
    assert "Photo 2 file is missing." in result["problems"]


def test_field_workers_cannot_run_verification(client, worker):
    report = submit(client, worker).json()
    assert client.get(f"{URL}/{report['id']}/verify", headers=worker).status_code == 403


# --- Hash and vocabulary ---------------------------------------------------------------


def _input(**overrides) -> ReportInput:
    base = dict(
        client_report_id=uuid.UUID(int=1),
        text="hatu pani",
        event_type="waterlogging",
        place_name="Mirpur 10",
        latitude=23.8069,
        longitude=90.3687,
        location_accuracy_m=15.0,
        observed_at=datetime(2026, 7, 14, 8, 45, tzinfo=DHAKA),
    )
    base.update(overrides)
    return ReportInput(**base)


def test_content_hash_is_deterministic_and_time_zone_independent():
    reporter = uuid.UUID(int=7)
    a = content_hash(reporter_id=reporter, data=_input(), photo_sha256s=["ab"])
    same_instant_utc = _input(observed_at=datetime(2026, 7, 14, 2, 45, tzinfo=UTC))
    assert a == content_hash(reporter_id=reporter, data=_input(), photo_sha256s=["ab"])
    assert a == content_hash(reporter_id=reporter, data=same_instant_utc, photo_sha256s=["ab"])


@pytest.mark.parametrize(
    "change",
    [
        {"text": "hatu pani!"},
        {"event_type": "flood"},
        {"place_name": "Mirpur 11"},
        {"latitude": 23.8070},
        {"location_accuracy_m": 16.0},
        {"observed_at": datetime(2026, 7, 14, 8, 46, tzinfo=DHAKA)},
    ],
)
def test_any_change_changes_the_hash(change):
    reporter = uuid.UUID(int=7)
    base = content_hash(reporter_id=reporter, data=_input(), photo_sha256s=["ab"])
    assert base != content_hash(reporter_id=reporter, data=_input(**change), photo_sha256s=["ab"])
    assert base != content_hash(reporter_id=reporter, data=_input(), photo_sha256s=["ac"])
    assert base != content_hash(reporter_id=uuid.UUID(int=8), data=_input(), photo_sha256s=["ab"])


def test_event_types_match_the_dataset_schema():
    schema = Path(__file__).resolve().parents[2] / "data" / "schema" / "v1" / "common.schema.json"
    enum = json.loads(schema.read_text(encoding="utf-8"))["$defs"]["event_type"]["enum"]
    assert set(enum) == EVENT_TYPES
