"""Copy the extraction module (ai/extraction) into the backend (app/extraction)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "ai" / "extraction" / "carcux_extraction"
TARGET = ROOT / "backend" / "app" / "extraction"
FILES = ["claims.py", "numbers.py", "language.py"]


def copied(name: str) -> str:
    return (
        (SOURCE / name).read_text(encoding="utf-8").replace("carcux_extraction.", "app.extraction.")
    )


if __name__ == "__main__":
    for name in FILES:
        (TARGET / name).write_text(copied(name), encoding="utf-8")
        print(f"copied {name}")
