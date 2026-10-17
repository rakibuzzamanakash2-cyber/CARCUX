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

    # Salt for dataset account_ref (a hash of a social account, never its handle). Set it
    # once and keep it, so the same account gets the same reference in every export;
    # unset, it is derived from the JWT secret.
    dataset_salt: SecretStr | None = None

    # Field report media (photos). Stored on disk, outside the database.
    media_dir: Path = Path("media")
    max_photos_per_report: int = 4
    # The frontend calls the API on behalf of browsers and passes the browser's address
    # in X-Forwarded-For. It is believed only from loopback and private-network
    # addresses (the frontend container); set false if the API port is exposed to a
    # network you do not trust.
    trust_forwarded_from_private: bool = True
    # Roles that must use two-factor sign-in. Until they set it up, they can only reach
    # their account page. Empty by default in development and tests; in production,
    # unset means admins and analysts (see the validator below).
    require_two_factor_roles: list[str] | None = None
    max_photo_bytes: int = 8 * 1024 * 1024

    # Public signals: reading outside sources (GDACS, news feeds, ReliefWeb).
    ingest_timeout_seconds: float = 20.0
    ingest_max_bytes: int = 5 * 1024 * 1024
    # Feeds on private or local addresses are refused unless this is set (tests, labs).
    ingest_allow_private_addresses: bool = False
    # ReliefWeb's API needs an approved app name (https://apidoc.reliefweb.int).
    reliefweb_appname: str | None = None

    # Public site: people sign up with an email address to like and comment. Links in
    # emails point here. Without an SMTP host, emails are written to the log instead.
    public_base_url: str = "http://localhost:3000"
    public_token_days: int = 14
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = True
    mail_from: str = "CARCUX <no-reply@carcux.local>"

    @model_validator(mode="after")
    def _production_requires_real_secret(self) -> "Settings":
        if self.environment == "production":
            secret = self.jwt_secret.get_secret_value()
            if secret == DEV_JWT_SECRET or len(secret) < 32:
                raise ValueError("CARCUX_JWT_SECRET must be set to 32+ random characters")
        return self

    @property
    def two_factor_roles(self) -> frozenset[str]:
        """Roles that must use two-factor sign-in."""
        if self.require_two_factor_roles is not None:
            return frozenset(self.require_two_factor_roles)
        return frozenset({"admin", "analyst"}) if self.environment == "production" else frozenset()

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
