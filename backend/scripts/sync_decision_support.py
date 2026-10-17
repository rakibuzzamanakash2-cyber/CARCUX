"""Copy the decision support module (ai/decision_support) into the backend
(app/decision_support), as sync_extraction.py does for extraction."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "ai" / "decision_support" / "carcux_decision_support"
TARGET = ROOT / "backend" / "app" / "decision_support"
FILES = ["__init__.py", "model.py", "priority.py", "summary.py", "changes.py"]


def copied(name: str) -> str:
    text = (SOURCE / name).read_text(encoding="utf-8")
    return text.replace("carcux_decision_support.", "app.decision_support.")


if __name__ == "__main__":
    TARGET.mkdir(exist_ok=True)
    for name in FILES:
        (TARGET / name).write_text(copied(name), encoding="utf-8")
        print(f"copied {name}")
