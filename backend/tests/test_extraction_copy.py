"""The backend's copy of the extraction module matches the original in ai/extraction."""

import importlib.util
from pathlib import Path

import pytest

from app.extraction import detect_language, extract

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend" / "scripts" / "sync_extraction.py"


@pytest.mark.skipif(
    not (ROOT / "ai" / "extraction").exists(), reason="the AI modules are not checked out"
)
def test_copy_matches_the_original():
    spec = importlib.util.spec_from_file_location("sync_extraction", SCRIPT)
    sync = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync)
    for name in sync.FILES:
        here = (sync.TARGET / name).read_text(encoding="utf-8")
        assert here == sync.copied(name), (
            f"app/extraction/{name} differs from ai/extraction: "
            "run python backend/scripts/sync_extraction.py"
        )
    for name in sync.DATA:
        assert (sync.TARGET / name).read_bytes() == (sync.SOURCE / name).read_bytes(), (
            f"app/extraction/{name} differs from ai/extraction: "
            "run python backend/scripts/sync_extraction.py"
        )


def test_it_works_inside_the_backend():
    claims = {c.attribute: c.value for c in extract("Mirpur 10 e hatu pani, 3 jon mara geche")}
    assert claims == {"magnitude": "knee-deep", "casualty_count": 3}
    assert detect_language("টানা বৃষ্টিতে হাঁটুসমান পানি") == "bn"
