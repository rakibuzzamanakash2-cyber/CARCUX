"""Field-report photos with ai/media's hashes and OCR (app/media_features)."""

import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageOps
from sqlalchemy import select

from app.media_features import ocr
from app.models.field_report import FieldReportMedia
from app.models.user import Role
from app.services import photo_text
from app.services.dataset import _photo
from app.services.media import photo_match
from tests.test_field_reports import URL, flags_of, photo, submit

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend" / "scripts" / "sync_media.py"


@pytest.fixture
def worker(make_user, login):
    make_user("worker@office.local", Role.FIELD_WORKER)
    return login("worker@office.local")


@pytest.fixture
def worker2(make_user, login):
    make_user("worker2@office.local", Role.FIELD_WORKER)
    return login("worker2@office.local")


@pytest.fixture
def fake_ocr(monkeypatch):
    """Tesseract as if installed, reading a fixed text (CI has no tesseract)."""
    calls = []

    def read(image, *a, **kw):
        calls.append(image.size)
        return ocr.OCRResult("Mirpur 10 golchottor\nহাঁটু পানি 01711-234567", 81.24)

    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setattr(ocr, "read_text", read)
    return calls


def _png(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


@pytest.mark.skipif(
    not (ROOT / "ai" / "media").exists(), reason="the AI modules are not checked out"
)
def test_copy_matches_the_original():
    spec = importlib.util.spec_from_file_location("sync_media", SCRIPT)
    sync = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync)
    for name in sync.FILES:
        assert (sync.TARGET / name).read_text(encoding="utf-8") == sync.copied(name), (
            f"app/media_features/{name} differs from ai/media: "
            "run python backend/scripts/sync_media.py"
        )


def test_new_photos_get_all_four_hashes(client, worker, db):
    submit(client, worker, photos=[photo(3)])
    m = db.scalars(select(FieldReportMedia)).one()
    assert all(len(h) == 16 for h in (m.dhash, m.phash, m.dhash_mirrored, m.phash_mirrored))
    assert m.ocr_status is None  # read later by the worker


def test_mirrored_copy_is_flagged(client, worker, worker2):
    original = photo(11, size=(640, 480))
    flipped = _png(ImageOps.mirror(Image.open(io.BytesIO(original))))
    submit(client, worker, photos=[original])
    response = submit(client, worker2, photos=[flipped])
    assert "photo_reused" in flags_of(response)
    assert "a mirrored copy of" in response.text


def test_photos_stored_before_phash_are_compared_by_dhash(client, worker, worker2, db):
    original = photo(7, size=(640, 480))
    submit(client, worker, photos=[original])
    m = db.scalars(select(FieldReportMedia)).one()
    m.phash = m.dhash_mirrored = m.phash_mirrored = None
    db.commit()
    resized = io.BytesIO()
    Image.open(io.BytesIO(original)).resize((320, 240)).save(resized, "JPEG", quality=80)
    assert "photo_reused" in flags_of(submit(client, worker2, photos=[resized.getvalue()]))
    assert "photo_reused" not in flags_of(submit(client, worker2, photos=[photo(9)]))


def test_photo_match_rules():
    a = {
        "dhash": "0" * 16,
        "phash": "0" * 16,
        "dhash_mirrored": "f" * 16,
        "phash_mirrored": "f" * 16,
    }
    near = {**a, "dhash": "00000000000003ff"}  # 10 bits apart: still the same picture
    far = {k: "f0f0f0f0f0f0f0f0" for k in a}
    assert photo_match(near, a) == "near-identical"
    assert photo_match(far, a) is None
    # Only dhashes on one side: the old rule, at most 6 bits.
    old = {
        "dhash": "000000000000003f",
        "phash": None,
        "dhash_mirrored": None,
        "phash_mirrored": None,
    }
    assert photo_match(a, old) == "near-identical"
    assert photo_match(a, {**old, "dhash": "00000000000000ff"}) is None


def test_worker_reads_text_in_photos(client, worker, db, settings, fake_ocr):
    report = submit(client, worker, photos=[photo(1), photo(2)]).json()
    done = photo_text.process(db, settings)
    assert (done.read, done.failed, done.waiting) == (2, 0, 0)
    body = client.get(f"{URL}/{report['id']}", headers=worker).json()
    first = body["media"][0]
    assert first["ocr_status"] == "done" and first["ocr_confidence"] == 81.2
    assert first["ocr_text"].startswith("Mirpur 10 golchottor")
    # Nothing left: a second pass reads nothing.
    assert photo_text.process(db, settings).read == 0 and len(fake_ocr) == 2


def test_without_tesseract_photos_wait_but_get_hashes(client, worker, db, settings, monkeypatch):
    monkeypatch.setattr(ocr, "available", lambda: False)
    submit(client, worker, photos=[photo(4)])
    m = db.scalars(select(FieldReportMedia)).one()
    m.phash = m.dhash_mirrored = m.phash_mirrored = None
    db.commit()
    done = photo_text.process(db, settings)
    assert (done.hashed, done.read) == (1, 0)
    db.refresh(m)
    assert m.phash and m.ocr_status is None


def test_missing_file_is_marked_failed_once(client, worker, db, settings, fake_ocr):
    submit(client, worker, photos=[photo(5)])
    m = db.scalars(select(FieldReportMedia)).one()
    (settings.media_dir / m.storage_key).unlink()
    assert photo_text.process(db, settings).failed == 1
    assert photo_text.process(db, settings).failed == 0
    db.refresh(m)
    assert m.ocr_status == "failed"


def test_dataset_photo_features_are_redacted_excerpts():
    m = SimpleNamespace(dhash="ABCDEF0123456789", phash=None, ocr_text=None)
    assert _photo(m) == {"kind": "image", "phash": "abcdef0123456789"}
    m = SimpleNamespace(
        dhash="abcdef0123456789",
        phash="0123456789abcdef",
        ocr_text="Call 01711-234567\n" + "x" * 400,
    )
    out = _photo(m)
    assert out["phash"] == "0123456789abcdef"
    assert out["ocr_text"].startswith("Call [PHONE] x") and len(out["ocr_text"]) <= 300


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("01711234567", "[PHONE]"),
        ("+8801711234567", "[PHONE]"),
        ("call 01711-234567 now", "call [PHONE] now"),
        ("+880 1711 234 567", "[PHONE]"),
        ("1500 people, 2024-08-21", "1500 people, 2024-08-21"),
        ("017112345678", "017112345678"),  # 12 digits: not a phone number
    ],
)
def test_phone_numbers_are_redacted_however_written(text, expected):
    from app.services.dataset import _redact

    assert _redact(text) == expected
