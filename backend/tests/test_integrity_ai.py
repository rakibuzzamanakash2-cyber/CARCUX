"""The checks and the account score from ai/integrity, inside the backend."""

import importlib.util
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.models.user import Role

URL = "/api/v1/field-reports"
RISK = "/api/v1/users/risk"
DHAKA = timezone(timedelta(hours=6))
MIRPUR = (23.8069, 90.3687)
ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend" / "scripts" / "sync_integrity.py"
LONG = (
    "Breaking: dam gates opened upstream, everyone in the district must leave "
    "immediately tonight, share with everyone"
)


def submit(client, headers, text, where=MIRPUR):
    data = {
        "client_report_id": str(uuid.uuid4()),
        "text": text,
        "latitude": str(where[0]),
        "longitude": str(where[1]),
        "location_accuracy_m": "15",
        "observed_at": datetime.now(DHAKA).isoformat(),
    }
    response = client.post(URL, data=data, headers=headers)
    assert response.status_code == 201, response.text
    return {f["code"] for f in response.json()["integrity_flags"]}


@pytest.fixture
def worker(make_user, login):
    make_user("worker@office.local", Role.FIELD_WORKER, full_name="Worker One")
    return login("worker@office.local")


@pytest.fixture
def worker2(make_user, login):
    make_user("worker2@office.local", Role.FIELD_WORKER, full_name="Worker Two")
    return login("worker2@office.local")


@pytest.mark.skipif(
    not (ROOT / "ai" / "integrity").exists(), reason="the AI modules are not checked out"
)
def test_copy_matches_the_original():
    spec = importlib.util.spec_from_file_location("sync_integrity", SCRIPT)
    sync = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync)
    for name in sync.FILES:
        assert (sync.TARGET / name).read_text(encoding="utf-8") == sync.copied(name), (
            f"app/integrity/{name} differs from ai/integrity: "
            "run python backend/scripts/sync_integrity.py"
        )


def test_text_naming_a_far_place_is_flagged(client, worker):
    assert "location_text_mismatch" in submit(client, worker, "Sylhet shohore pani uthse")
    assert "location_text_mismatch" not in submit(client, worker, "Mirpur 10 e hatu pani")


def test_long_report_copied_from_another_account_is_flagged(client, worker, worker2):
    assert "copied_text" not in submit(client, worker, LONG)
    # The same worker repeating itself is not copying; another account is.
    assert "copied_text" not in submit(client, worker, LONG)
    assert "copied_text" in submit(client, worker2, LONG)


def test_short_reports_alike_are_not_copying(client, worker, worker2):
    text = "Mirpur 10 golchottor e hatu pani, bus cholche na."
    submit(client, worker, text)
    assert "copied_text" not in submit(client, worker2, text)


def test_account_risk_lists_field_workers_highest_first(client, worker, worker2, admin_headers):
    for _ in range(3):
        submit(client, worker, "Sylhet shohore pani uthse")
    submit(client, worker2, "Mirpur 10 e hatu pani")
    rows = client.get(RISK, headers=admin_headers).json()
    assert [r["full_name"] for r in rows] == ["Worker One", "Worker Two"]
    top, other = rows
    assert top["score"] >= 0.5 and top["recent"] == 3
    assert any("location_text_mismatch" in x for x in top["reasons"])
    # No history yet: compared with its flags only, and it has none.
    assert other["score"] == 0.0
    assert other["reasons"] == ["Only 0 earlier reports: compared with its flags only."]


def test_only_admins_see_account_risk(client, worker, make_user, login):
    assert client.get(RISK, headers=worker).status_code == 403
    make_user("analyst@office.local", Role.ANALYST)
    assert client.get(RISK, headers=login("analyst@office.local")).status_code == 403
