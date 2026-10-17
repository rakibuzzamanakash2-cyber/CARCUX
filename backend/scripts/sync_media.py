"""Copy the media module's hashing and OCR (ai/media) into the backend (app/media_features)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "ai" / "media" / "carcux_media"
TARGET = ROOT / "backend" / "app" / "media_features"
FILES = ["hashing.py", "ocr.py"]


def copied(name: str) -> str:
    return (
        (SOURCE / name).read_text(encoding="utf-8").replace("carcux_media.", "app.media_features.")
    )


if __name__ == "__main__":
    TARGET.mkdir(exist_ok=True)
    for name in FILES:
        (TARGET / name).write_text(copied(name), encoding="utf-8")
        print(f"copied {name}")
