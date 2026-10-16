"""Perceptual hashes of images and video frames, for spotting reused media (the
dataset's `same_media` dependence, and old photos posted as new).

Two 64-bit hashes, each also of the mirrored image (a flipped repost): `dhash`, the
difference hash the backend already stores for field report photos
(backend/app/services/media.py), so hashes from both compare directly; and `phash`, a
DCT hash. Two images are the same picture when either hash, as is or mirrored, is at
most SAME_IMAGE_BITS apart. They survive resizing, recompression, brightness and
contrast, small crops, watermarks and slight rotation; heavy crops and a photo framed
inside a screenshot are mostly missed (README). All are 16 hex characters, the dataset's
`media[].phash` format.
"""

import numpy as np
from PIL import Image, ImageOps

SAME_IMAGE_BITS = 10  # at most this many of 64 bits apart: the same picture (README)


def dhash(image: Image.Image) -> str:
    """64-bit difference hash (identical to the backend's)."""
    small = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(small.tobytes())
    bits = 0
    for row in range(8):
        for col in range(8):
            left, right = pixels[row * 9 + col], pixels[row * 9 + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"{bits:016x}"


def _dct_matrix(n: int) -> np.ndarray:
    k = np.arange(n)
    m = np.cos(np.pi * (2 * k[None, :] + 1) * k[:, None] / (2 * n))
    m[0] *= 1 / np.sqrt(2)
    return m * np.sqrt(2 / n)


_DCT32 = _dct_matrix(32)


def phash(image: Image.Image) -> str:
    """64-bit DCT hash: the low frequencies of a 32×32 grey image against their median."""
    small = np.asarray(image.convert("L").resize((32, 32), Image.Resampling.LANCZOS), float)
    low = (_DCT32 @ small @ _DCT32.T)[:8, :8].flatten()
    median = np.median(low[1:])  # leave out the overall brightness
    bits = 0
    for v in low:
        bits = (bits << 1) | (1 if v > median else 0)
    return f"{bits:016x}"


def hamming(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


def hashes(image: Image.Image) -> dict[str, str]:
    """Both hashes of the image and of its mirror image."""
    mirrored = ImageOps.mirror(image)
    return {"dhash": dhash(image), "dhash_mirrored": dhash(mirrored),
            "phash": phash(image), "phash_mirrored": phash(mirrored)}  # fmt: skip


def distance(a: dict[str, str], b: dict[str, str], kind: str = "both") -> int:
    """Bits apart: the closest of the hashes (`kind` "dhash", "phash" or "both"), with
    either image as it is or mirrored."""
    kinds = ("dhash", "phash") if kind == "both" else (kind,)
    return min(min(hamming(a[k], b[k]), hamming(a[k], b[f"{k}_mirrored"])) for k in kinds)


def same_image(a: dict[str, str], b: dict[str, str], bits: int = SAME_IMAGE_BITS) -> bool:
    """Whether two images' hashes (from `hashes`) are the same picture."""
    return distance(a, b) <= bits
