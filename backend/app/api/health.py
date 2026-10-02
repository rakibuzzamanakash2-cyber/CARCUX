"""Liveness endpoint. A readiness check (database, Redis) is added with the database layer."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app import __version__
from app.core.config import Settings, app_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(app_settings)) -> HealthResponse:  # noqa: B008
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=__version__,
        environment=settings.environment,
    )
