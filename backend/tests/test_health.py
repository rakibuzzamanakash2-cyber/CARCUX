from fastapi.testclient import TestClient

from app import __version__
from app.core.config import Settings
from app.main import create_app


def make_client(**overrides) -> TestClient:
    settings = Settings(**{"environment": "test", **overrides})
    return TestClient(create_app(settings))


def test_health_returns_ok():
    response = make_client().get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["environment"] == "test"


def test_docs_enabled_outside_production():
    assert make_client().get("/docs").status_code == 200


def test_docs_disabled_in_production():
    client = make_client(environment="production")

    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
