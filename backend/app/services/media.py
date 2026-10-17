"""Photo validation, hashing and storage for field reports."""

import hashlib
import io
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.media_features import hashing

# Only these formats are accepted. The type is decided by decoding the bytes,
# never by the file name or the browser's Content-Type header.
ALLOWED_FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}

# Refuse images that would take huge memory to decode ("decompression bombs").
MAX_PIXELS = 40_000_000
# Photos stored before perceptual hashes existed have only a dhash: compared by it alone,
# at the old, stricter threshold.
DHASH_ONLY_BITS = 6


class InvalidMediaError(ValueError):
    pass


@dataclass(frozen=True)
class CheckedPhoto:
    data: bytes
    content_type: str
    extension: str
    width: int
    height: int
    sha256: str
    dhash: str
    phash: str | None = None
    dhash_mirrored: str | None = None
    phash_mirrored: str | None = None

    @property
    def hashes(self) -> dict[str, str | None]:
        return photo_hashes(self)


dhash = hashing.dhash
hamming = hashing.hamming


def photo_hashes(photo) -> dict[str, str | None]:
    """The hashes of a CheckedPhoto or a stored FieldReportMedia row."""
    return {k: getattr(photo, k) for k in ("dhash", "phash", "dhash_mirrored", "phash_mirrored")}


def photo_match(a: dict[str, str | None], b: dict[str, str | None]) -> str | None:
    """How photo `a` matches photo `b`: "near-identical", "mirrored", or None.

    With all four hashes on both sides: ai/media's rule (either hash, as is or mirrored,
    at most hashing.SAME_IMAGE_BITS apart; README there). Otherwise the dhashes alone, at
    DHASH_ONLY_BITS."""
    if all(a.values()) and all(b.values()):
        straight = min(hamming(a["dhash"], b["dhash"]), hamming(a["phash"], b["phash"]))
        if straight <= hashing.SAME_IMAGE_BITS:
            return "near-identical"
        flipped = min(
            hamming(a["dhash_mirrored"], b["dhash"]), hamming(a["phash_mirrored"], b["phash"])
        )
        return "mirrored" if flipped <= hashing.SAME_IMAGE_BITS else None
    if a["dhash"] and b["dhash"] and hamming(a["dhash"], b["dhash"]) <= DHASH_ONLY_BITS:
        return "near-identical"
    return None


def check_photo(data: bytes, max_bytes: int, label: str) -> CheckedPhoto:
    if not data:
        raise InvalidMediaError(f"{label} is empty")
    if len(data) > max_bytes:
        raise InvalidMediaError(f"{label} is larger than {max_bytes // (1024 * 1024)} MB")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            width, height = probe.size
            if width * height > MAX_PIXELS:
                raise InvalidMediaError(f"{label} has too many pixels")
            probe.verify()  # structural check without full decode
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            found = hashing.hashes(image)
    except InvalidMediaError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise InvalidMediaError(f"{label} is not a valid image") from None

    if fmt not in ALLOWED_FORMATS:
        raise InvalidMediaError(f"{label} must be JPEG, PNG or WebP")
    content_type, extension = ALLOWED_FORMATS[fmt]
    return CheckedPhoto(
        data=data,
        content_type=content_type,
        extension=extension,
        width=width,
        height=height,
        sha256=hashlib.sha256(data).hexdigest(),
        **found,
    )


def storage_key_for(report_id: uuid.UUID, media_id: uuid.UUID, extension: str) -> str:
    return f"field_reports/{report_id}/{media_id}.{extension}"


def resolve(media_dir: Path, storage_key: str) -> Path:
    """Absolute path for a stored key, refusing anything that escapes the media dir."""
    root = media_dir.resolve()
    path = (root / storage_key).resolve()
    if not path.is_relative_to(root):
        raise InvalidMediaError("invalid storage key")
    return path


def file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
