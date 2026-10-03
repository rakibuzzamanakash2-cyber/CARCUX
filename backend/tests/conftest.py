"""Test fixtures. Tests run against a real PostgreSQL database (CARCUX_TEST_DATABASE_URL)."""

import importlib.util
import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import make_engine, make_session_factory
from app.main import create_app
from app.models.user import Role, User
from app.services.users import create_user

TEST_DATABASE_URL = os.environ.get(
    "CARCUX_TEST_DATABASE_URL",
    "postgresql+psycopg://carcux:carcux@127.0.0.1:5432/carcux_test",
)
BACKEND_DIR = Path(__file__).resolve().parents[1]
PASSWORD = "correct-horse-battery-staple"  # noqa: S105


def _seed_sources() -> list[tuple]:
    """The starting sources, exactly as migration 0005 inserts them."""
    path = next((BACKEND_DIR / "migrations" / "versions").glob("0005_*.py"))
    spec = importlib.util.spec_from_file_location("m0005", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.SEED_SOURCES


SEED_SOURCES = _seed_sources()


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    eng = make_engine(TEST_DATABASE_URL)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def _clean_tables(request) -> None:
    # Only for tests that touch the database. TRUNCATE is not blocked by the
    # audit log's row-level trigger, so it can reset the append-only table.
    if "engine" not in request.fixturenames:
        return
    eng = request.getfixturevalue("engine")
    with eng.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE event_evidence, events, field_report_media, field_reports, "
                "signals, ingest_runs, sources, audit_log, users RESTART IDENTITY CASCADE"
            )
        )
        for key, name, stype, adapter, url, domain, lang, enabled, every in SEED_SOURCES:
            conn.execute(
                text(
                    "INSERT INTO sources (id, key, name, source_type, adapter, url, domain, "
                    "language, enabled, interval_minutes) VALUES (:id, :key, :name, :stype, "
                    ":adapter, :url, :domain, :lang, :enabled, :every)"
                ),
                {"id": uuid.uuid4(), "key": key, "name": name, "stype": stype,
                 "adapter": adapter, "url": url, "domain": domain, "lang": lang,
                 "enabled": enabled, "every": every},
            )  # fmt: skip


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        environment="test", database_url=TEST_DATABASE_URL, media_dir=tmp_path / "media"
    )


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    with make_session_factory(engine)() as session:
        yield session


@pytest.fixture
def client(engine: Engine, settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def make_user(db: Session):
    def _make(email: str = "staff@example.com", role: Role = Role.ANALYST, **kw) -> User:
        user = create_user(
            db,
            email=email,
            full_name=kw.pop("full_name", "Test User"),
            password=kw.pop("password", PASSWORD),
            role=role,
            actor_id=None,
        )
        for key, value in kw.items():
            setattr(user, key, value)
        db.commit()
        return user

    return _make


@pytest.fixture
def login(client: TestClient):
    def _login(email: str, password: str = PASSWORD) -> dict[str, str]:
        response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login


@pytest.fixture
def admin_headers(make_user, login) -> dict[str, str]:
    make_user("admin@example.com", Role.ADMIN)
    return login("admin@example.com")
