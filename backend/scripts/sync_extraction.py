"""Copy the extraction module (ai/extraction) into the backend (app/extraction)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "ai" / "extraction" / "carcux_extraction"
TARGET = ROOT / "backend" / "app" / "extraction"
FILES = ["claims.py", "numbers.py", "language.py", "places.py", "times.py"]
DATA = ["data/bd_gazetteer.json"]


def copied(name: str) -> str:
    return (
        (SOURCE / name).read_text(encoding="utf-8").replace("carcux_extraction.", "app.extraction.")
    )


if __name__ == "__main__":
    for name in FILES:
        (TARGET / name).write_text(copied(name), encoding="utf-8")
        print(f"copied {name}")
    for name in DATA:
        (TARGET / name).parent.mkdir(exist_ok=True)
        (TARGET / name).write_bytes((SOURCE / name).read_bytes())
        print(f"copied {name}")
