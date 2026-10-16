"""The backend's copy of the decision support module matches ai/decision_support."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend" / "scripts" / "sync_decision_support.py"


@pytest.mark.skipif(
    not (ROOT / "ai" / "decision_support").exists(), reason="the AI modules are not checked out"
)
def test_copy_matches_the_original():
    spec = importlib.util.spec_from_file_location("sync_decision_support", SCRIPT)
    sync = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync)
    for name in sync.FILES:
        here = (sync.TARGET / name).read_text(encoding="utf-8")
        assert here == sync.copied(name), (
            f"app/decision_support/{name} differs from ai/decision_support: "
            "run python backend/scripts/sync_decision_support.py"
        )
