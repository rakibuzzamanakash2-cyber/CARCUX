"""Test fixtures. Tests run against a real PostgreSQL database (CARCUX_TEST_DATABASE_URL)."""

import os
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
        conn.execute(text("TRUNCATE audit_log, users RESTART IDENTITY CASCADE"))


@pytest.fixture
def settings() -> Settings:
    return Settings(environment="test", database_url=TEST_DATABASE_URL)


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
