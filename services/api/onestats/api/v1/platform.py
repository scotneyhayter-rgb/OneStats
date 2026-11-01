"""Platform ("All Workspaces") dashboard API — Super Administrator only.

A cross-workspace overview for the platform administrator. Super-Admin-gated server-side (not
merely hidden in the UI). Read-only; preserves FORCE RLS (per-workspace counts are read under each
workspace's own context). Totals are workspace record counts, not global-unique figures.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from onestats import __version__
from onestats.api.deps import SettingsDep, require_super_admin
from onestats.db.session import get_engine
from onestats.domain import platform, updates

router = APIRouter(prefix="/platform", tags=["platform"])
SuperAdmin = Annotated[dict, Depends(require_super_admin)]


@router.get("/dashboard")
def platform_dashboard(admin: SuperAdmin, settings: SettingsDep) -> dict[str, Any]:
    engine = get_engine(settings)
    if engine is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    data = platform.platform_dashboard(engine)
    # enrich system health with runtime facts the domain layer does not own
    data["system_health"].update({
        "version": __version__,
        "env": settings.env,
        "maintenance_mode": updates.is_maintenance(engine),
    })
    return data
