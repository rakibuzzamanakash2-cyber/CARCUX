"""Work on stored field-report photos after submission, in the worker: fill in hashes
for photos stored before perceptual hashes existed, and read the text in each photo
(Bangla and English, with ai/media's OCR).

OCR runs here rather than during submission because it takes seconds a photo, and a
field worker on a weak connection should not wait for it. Without the tesseract program
photos simply wait (ocr_status stays empty) until it is installed.
"""

import io
import logging
from dataclasses import dataclass

from PIL import Image
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.media_features import hashing, ocr
from app.models.field_report import FieldReportMedia
from app.services.media import resolve

log = logging.getLogger(__name__)
BATCH = 20  # photos per pass; the worker runs a pass every minute
OCR_TEXT_MAX = 2000  # characters kept; the dataset export shortens further


@dataclass
class Pass:
    hashed: int = 0
    read: int = 0
    failed: int = 0
    waiting: int = 0  # still needing OCR after this pass


def _image(settings: Settings, m: FieldReportMedia) -> Image.Image:
    data = resolve(settings.media_dir, m.storage_key).read_bytes()
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


def process(db: Session, settings: Settings, limit: int = BATCH) -> Pass:
    """One pass over photos that need hashes or OCR."""
    result = Pass()
    can_read = ocr.available()
    # A photo that could not be opened is marked "failed" and not tried again.
    needs_hashes = and_(
        FieldReportMedia.phash.is_(None),
        or_(FieldReportMedia.ocr_status.is_(None), FieldReportMedia.ocr_status != "failed"),
    )
    pending = or_(needs_hashes, FieldReportMedia.ocr_status.is_(None)) if can_read else needs_hashes
    rows = db.scalars(
        select(FieldReportMedia).where(pending).order_by(FieldReportMedia.id).limit(limit)
    ).all()
    for m in rows:
        try:
            image = _image(settings, m)
        except (OSError, ValueError) as exc:
            log.warning("photo %s: cannot open (%s)", m.id, exc)
            m.ocr_status, result.failed = "failed", result.failed + 1
            continue
        if m.phash is None:
            found = hashing.hashes(image)
            m.phash, m.dhash_mirrored = found["phash"], found["dhash_mirrored"]
            m.phash_mirrored = found["phash_mirrored"]
            result.hashed += 1
        if can_read and m.ocr_status is None:
            try:
                text = ocr.read_text(image)
            except Exception as exc:  # a crash in tesseract must not stop the worker
                log.warning("photo %s: OCR failed (%s)", m.id, exc)
                m.ocr_status, result.failed = "failed", result.failed + 1
                continue
            m.ocr_text = text.text[:OCR_TEXT_MAX] or None
            m.ocr_confidence = round(text.confidence, 1) if text.confidence is not None else None
            m.ocr_status = "done"
            result.read += 1
    db.commit()
    if can_read:
        result.waiting = db.scalar(
            select(func.count()).where(FieldReportMedia.ocr_status.is_(None))
        )
    return result
