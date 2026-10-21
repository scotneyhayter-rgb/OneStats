"""Health and readiness endpoints (API v1)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from onestats import __version__
from onestats.core.config import Settings, get_settings
from onestats.db.session import check_connection

router = APIRouter(tags=["health"])

SettingsDep = Annotated[Settings, Depends(get_settings)]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    env: str


class DbHealthResponse(BaseModel):
    database_configured: bool
    database_connected: bool
    detail: str


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
def health(settings: SettingsDep) -> HealthResponse:
    """Liveness: the API process is up. Does not require a database."""
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=__version__,
        env=settings.env,
    )


@router.get("/health/db", response_model=DbHealthResponse, summary="Database readiness")
def health_db(settings: SettingsDep) -> DbHealthResponse:
    """Readiness: reports whether the database is configured and reachable.

    Returns 200 with the status either way so the desktop app can show a clear state;
    a missing credential is reported as not-configured, not as a server error.
    """
    st = check_connection(settings)
    return DbHealthResponse(
        database_configured=st.configured,
        database_connected=st.connected,
        detail=st.detail,
    )
