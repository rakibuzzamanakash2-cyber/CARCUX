from datetime import datetime, timedelta

import pytest

from app.models.user import Role
from tests.test_field_reports import DHAKA, photo, submit

URL = "/api/v1/overview"


@pytest.fixture
def worker(make_user, login):
    make_user("worker@office.local", Role.FIELD_WORKER)
    return login("worker@office.local")


@pytest.fixture
def worker2(make_user, login):
    make_user("worker2@office.local", Role.FIELD_WORKER)
    return login("worker2@office.local")


@pytest.fixture
def analyst(make_user, login):
    make_user("analyst@office.local", Role.ANALYST)
    return login("analyst@office.local")


def event(client, headers, **overrides):
    body = {
        "title": "Waterlogging at Mirpur 10",
        "event_type": "waterlogging",
        "latitude": 23.8069,
        "longitude": 90.3687,
        "started_at": datetime.now(DHAKA).isoformat(),
    }
    body.update(overrides)
    response = client.post("/api/v1/events", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_overview_counts_for_reviewers(client, analyst, worker, worker2):
    event(client, analyst, priority="critical")
    event(client, analyst, priority="high")
    closed = event(client, analyst, priority="high")
    client.patch(f"/api/v1/events/{closed['id']}", json={"status": "resolved"}, headers=analyst)
    submit(client, worker, photos=[photo(1)])
    submit(client, worker2, photos=[photo(1)])  # reused photo: flagged
    old = (datetime.now(DHAKA) - timedelta(days=3)).isoformat()
    submit(client, worker2, observed_at=old, latitude=24.9, longitude=91.8)

    body = client.get(URL, headers=analyst).json()

    assert body["open_events"] == 2
    assert body["open_by_priority"] == {"low": 0, "medium": 0, "high": 1, "critical": 1}
    assert body["reports_24h"] == 2
    assert body["flagged_24h"] == 1
    assert body["unreviewed_reports"] == 3


def test_overview_for_field_worker_is_own_and_without_review_numbers(client, worker, worker2):
    submit(client, worker)
    submit(client, worker2)

    body = client.get(URL, headers=worker).json()

    assert body["reports_24h"] == 1
    assert body["flagged_24h"] is None
    assert body["unreviewed_reports"] is None


def test_overview_needs_sign_in(client):
    assert client.get(URL).status_code == 401


def test_reports_since_filter(client, analyst, worker):
    submit(client, worker, observed_at=(datetime.now(DHAKA) - timedelta(days=2)).isoformat())
    recent = submit(client, worker).json()
    since = (datetime.now(DHAKA) - timedelta(hours=24)).isoformat()

    page = client.get("/api/v1/field-reports", params={"since": since}, headers=analyst).json()

    assert [r["id"] for r in page["items"]] == [recent["id"]]
    naive = client.get(
        "/api/v1/field-reports", params={"since": "2026-10-01T00:00:00"}, headers=analyst
    )
    assert naive.status_code == 422


def test_reports_search(client, analyst, worker):
    hit = submit(
        client, worker, text="Rasta bondho at Mohakhali flyover", place_name="Mohakhali"
    ).json()
    submit(client, worker, text="Pani at Mirpur", place_name="Mirpur 10")

    page = client.get("/api/v1/field-reports", params={"q": "mohakhali"}, headers=analyst).json()

    assert [r["id"] for r in page["items"]] == [hit["id"]]
    by_place = client.get("/api/v1/field-reports", params={"q": "mirpur 10"}, headers=analyst)
    assert by_place.json()["total"] == 1
