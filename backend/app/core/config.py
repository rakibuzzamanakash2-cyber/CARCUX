"""Application settings, loaded from environment variables (prefix CARCUX_) or .env."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import Request
from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-secret-change-me-0000000000"  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CARCUX_", env_file=".env", extra="ignore")

    app_name: str = "CARCUX API"
    environment: Literal["development", "test", "production"] = "development"
    api_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://carcux:carcux@localhost:5432/carcux"
    redis_url: str = "redis://localhost:6379/0"

    cors_origins: list[str] = ["http://localhost:3000"]

    # Auth
    jwt_secret: SecretStr = SecretStr(DEV_JWT_SECRET)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30

    # Field report media (photos). Stored on disk, outside the database.
    media_dir: Path = Path("media")
    max_photos_per_report: int = 4
    max_photo_bytes: int = 8 * 1024 * 1024

    @model_validator(mode="after")
    def _production_requires_real_secret(self) -> "Settings":
        if self.environment == "production":
            secret = self.jwt_secret.get_secret_value()
            if secret == DEV_JWT_SECRET or len(secret) < 32:
                raise ValueError("CARCUX_JWT_SECRET must be set to 32+ random characters")
        return self

    @property
    def docs_enabled(self) -> bool:
        # Interactive API docs are off in production.
        return self.environment != "production"


@lru_cache
def get_settings() -> Settings:
    """Settings from the environment. Used once, when the app is created."""
    return Settings()


def app_settings(request: Request) -> Settings:
    """Dependency: the settings this app instance was created with."""
    return request.app.state.settings
