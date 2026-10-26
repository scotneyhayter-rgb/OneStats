"""Update-system endpoints: version/compatibility capability, Super-Admin server-update controls,
maintenance mode, pre-update checks and the update audit history.

These endpoints are read/administrative only — they never download or run update packages. Server
and desktop update *execution* is performed by signed packages and privileged maintenance tooling
outside the ordinary API (docs/74-update-system.md), so no remote-command-execution surface exists.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from onestats.api.deps import CurrentUser, SettingsDep, require_super_admin
from onestats.core import version as ver
from onestats.db.session import get_engine
from onestats.domain import backups, updates

router = APIRouter(tags=["updates"])

SuperAdmin = Annotated[dict[str, Any], Depends(require_super_admin)]


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


# --- Public-to-authenticated compatibility capability -----------------------------------------

@router.get("/capability", summary="Server version & client compatibility capability")
def capability(user: CurrentUser, settings: SettingsDep) -> dict[str, Any]:
    """Minimal version/compatibility document the desktop reads to make update decisions.
    Authenticated (not public) and free of infrastructure details."""
    with _engine(settings).begin() as conn:
        return updates.capability(conn, settings)


@router.get("/updates/compatibility", summary="Evaluate a desktop version against this server")
def compatibility(user: CurrentUser, settings: SettingsDep,
                  desktop_version: Annotated[str | None, Query()] = None) -> dict[str, Any]:
    with _engine(settings).begin() as conn:
        result = updates.compatibility_for(conn, desktop_version)
    result["server_version"] = ver.SERVER_VERSION
    result["api_version"] = ver.API_VERSION
    return result


# --- Super-Admin system-update controls -------------------------------------------------------

@router.get("/system/updates/status", summary="System-update dashboard (Super Admin)")
def system_status(admin: SuperAdmin, settings: SettingsDep) -> dict[str, Any]:
    with _engine(settings).begin() as conn:
        cap = updates.capability(conn, settings)
        schema = updates.current_schema(conn)
        backup = updates.backup_readiness(settings)
        events = updates.list_events(conn, limit=20)
    last = events[0] if events else None
    return {
        "server_version": ver.SERVER_VERSION,
        "api_version": ver.API_VERSION,
        "channel": settings.release_channel,
        "database": schema,
        "maintenance": cap["maintenance"],
        "backup": backup,
        "release_service": {
            "configured": settings.release_manifest_url is not None,
            "manifest_url": settings.release_manifest_url,
        },
        "recent_events": events,
        "last_result": last,
    }


@router.get("/updates/history", summary="Update event history (Super Admin)")
def history(admin: SuperAdmin, settings: SettingsDep,
            limit: Annotated[int, Query(ge=1, le=500)] = 100) -> dict[str, Any]:
    with _engine(settings).begin() as conn:
        return {"events": updates.list_events(conn, limit=limit)}


@router.post("/system/updates/pre-check", summary="Run read-only pre-update checks (Super Admin)")
def pre_check(admin: SuperAdmin, settings: SettingsDep) -> dict[str, Any]:
    with _engine(settings).begin() as conn:
        result = updates.pre_update_checks(conn, settings)
        updates.record_event(conn, component="server", event="pre_check",
                             outcome="ok" if result["ready"] else "error",
                             actor=str(admin["id"]), from_version=ver.SERVER_VERSION,
                             detail={"ready": result["ready"]})
    return result


class MaintenanceRequest(BaseModel):
    on: bool
    message: str | None = Field(default=None, max_length=300)


@router.post("/system/updates/maintenance", summary="Enter/exit maintenance mode (Super Admin)")
def maintenance(body: MaintenanceRequest, admin: SuperAdmin, settings: SettingsDep) -> dict[str, Any]:
    with _engine(settings).begin() as conn:
        state = updates.set_maintenance(conn, str(admin["id"]), on=body.on, message=body.message)
    return {"maintenance": {"mode": bool(state["maintenance_mode"]), "message": state["maintenance_message"]}}


@router.get("/system/updates/backups", summary="List local database backups (Super Admin)")
def list_backups(admin: SuperAdmin, settings: SettingsDep) -> dict[str, Any]:
    return {"backups": backups.list_backups(settings)}


@router.post("/system/updates/backup", summary="Create & verify a local database backup (Super Admin)")
def create_backup(admin: SuperAdmin, settings: SettingsDep) -> dict[str, Any]:
    try:
        info = backups.create_backup(settings)
    except RuntimeError as exc:
        with _engine(settings).begin() as conn:
            updates.record_event(conn, component="database", event="backup", outcome="error",
                                 actor=str(admin["id"]), detail={"error": str(exc)[:300]})
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    with _engine(settings).begin() as conn:
        updates.record_event(conn, component="database", event="backup_validated", outcome="ok",
                             actor=str(admin["id"]), detail={"file": info["file"], "size_bytes": info["size_bytes"]})
    return info


@router.post("/system/updates/check", summary="Report the configured release service (Super Admin)")
def check(admin: SuperAdmin, settings: SettingsDep) -> dict[str, Any]:
    """Reports whether a remote release service is configured. The desktop's Tauri updater fetches
    and verifies the signed manifest directly from that HTTPS endpoint — the server never fetches
    arbitrary URLs on a client's behalf (no SSRF surface)."""
    configured = settings.release_manifest_url is not None
    return {
        "configured": configured,
        "manifest_url": settings.release_manifest_url,
        "channel": settings.release_channel,
        "server_version": ver.SERVER_VERSION,
        "note": None if configured else "No update service is configured on this server.",
    }
