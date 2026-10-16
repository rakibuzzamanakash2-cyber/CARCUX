"""Copy the integrity module (ai/integrity) into the backend (app/integrity)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "ai" / "integrity" / "carcux_integrity"
TARGET = ROOT / "backend" / "app" / "integrity"
FILES = ["checks.py", "account.py"]


def copied(name: str) -> str:
    return (
        (SOURCE / name)
        .read_text(encoding="utf-8")
        .replace("carcux_integrity.", "app.integrity.")
        .replace("carcux_extraction.", "app.extraction.")
    )


if __name__ == "__main__":
    TARGET.mkdir(exist_ok=True)
    for name in FILES:
        (TARGET / name).write_text(copied(name), encoding="utf-8")
        print(f"copied {name}")
