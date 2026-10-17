"""Text in images, in Bangla and English: signboards, screenshots of posts, news
tickers, handwritten notices (the dataset's `media[].ocr_text`).

Uses the Tesseract program with its Bangla and English models (Debian/Ubuntu:
`apt install tesseract-ocr tesseract-ocr-ben`; Windows: the UB Mannheim installer with
Bengali ticked). Small images (under 1000 pixels on their longer side, such as cropped
screenshots) are doubled first; larger ones are read as they are, because enlarging
text that is already large makes Tesseract worse. Words Tesseract is unsure of are
dropped, so the text is short rather than wrong.
"""

import csv
import io
import shutil
import subprocess
from dataclasses import dataclass, field

from PIL import Image, ImageOps

LANGUAGES = "ben+eng"
MIN_CONFIDENCE = 40  # Tesseract word confidence (0–100) below which a word is dropped
SMALL = 1000  # images whose longer side is shorter than this are doubled


class OCRUnavailableError(RuntimeError):
    pass


@dataclass
class OCRResult:
    text: str
    confidence: float | None  # mean word confidence, 0–100
    words: list[tuple[str, float]] = field(default_factory=list)


def available() -> bool:
    return shutil.which("tesseract") is not None


def _prepare(image: Image.Image) -> Image.Image:
    grey = ImageOps.exif_transpose(image).convert("L")
    if max(grey.size) < SMALL:
        grey = grey.resize((grey.width * 2, grey.height * 2), Image.Resampling.LANCZOS)
    return ImageOps.autocontrast(grey)


def read_text(image: Image.Image, languages: str = LANGUAGES, psm: int = 3) -> OCRResult:
    """The text Tesseract reads in the image, line by line."""
    if not available():
        raise OCRUnavailableError("the tesseract program is not installed")
    buf = io.BytesIO()
    _prepare(image).save(buf, format="PNG")
    out = subprocess.run(
        ["tesseract", "stdin", "stdout", "-l", languages, "--psm", str(psm), "tsv"],
        input=buf.getvalue(),
        capture_output=True,
        check=True,
        timeout=120,
    ).stdout.decode("utf-8", errors="replace")
    rows = list(csv.DictReader(io.StringIO(out), delimiter="\t", quoting=csv.QUOTE_NONE))
    lines: dict[tuple[str, str, str], list[str]] = {}
    words: list[tuple[str, float]] = []
    for r in rows:
        text = (r.get("text") or "").strip()
        conf = float(r.get("conf") or -1)
        if not text or conf < MIN_CONFIDENCE:
            continue
        words.append((text, conf))
        lines.setdefault((r["block_num"], r["par_num"], r["line_num"]), []).append(text)
    text = "\n".join(" ".join(ws) for ws in lines.values())
    mean = sum(c for _, c in words) / len(words) if words else None
    return OCRResult(text=text, confidence=mean, words=words)
