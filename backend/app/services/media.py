"""Photo validation, hashing and storage for field reports."""

import hashlib
import io
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

# Only these formats are accepted. The type is decided by decoding the bytes,
# never by the file name or the browser's Content-Type header.
ALLOWED_FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}

# Refuse images that would take huge memory to decode ("decompression bombs").
MAX_PIXELS = 40_000_000


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


def dhash(image: Image.Image) -> str:
    """64-bit difference hash: robust to resizing and recompression, not to cropping."""
    small = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(small.tobytes())  # one byte per pixel in mode "L"
    bits = 0
    for row in range(8):
        for col in range(8):
            left, right = pixels[row * 9 + col], pixels[row * 9 + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"{bits:016x}"


def hamming(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


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
            hash64 = dhash(image)
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
        dhash=hash64,
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
