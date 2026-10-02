"""Application settings, loaded from environment variables (prefix CARCUX_) or .env."""

from functools import lru_cache
from typing import Literal

from fastapi import Request
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CARCUX_", env_file=".env", extra="ignore")

    app_name: str = "CARCUX API"
    environment: Literal["development", "test", "production"] = "development"
    api_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://carcux:carcux@localhost:5432/carcux"
    redis_url: str = "redis://localhost:6379/0"

    cors_origins: list[str] = ["http://localhost:3000"]

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
