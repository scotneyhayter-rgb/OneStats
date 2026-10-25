"""Workspace dashboard API — the home-page command centre.

Real, database-backed summary for any member of the workspace (Super Admin, or a user with a role in it).
Read-only; enforces membership server-side, not merely by hiding controls. No fabricated values.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from onestats.api.deps import CurrentUser, SettingsDep
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import dashboard, workspaces

router = APIRouter(prefix="/workspaces/{workspace_id}/dashboard", tags=["dashboard"])


@router.get("")
def get_dashboard(workspace_id: UUID, user: CurrentUser, settings: SettingsDep) -> dict[str, Any]:
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    with workspace_transaction(eng, workspace_id, user["id"]) as conn:
        if not user["is_super_admin"] and not workspaces.user_is_member(conn, user["id"], workspace_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this workspace")
        return dashboard.workspace_dashboard(conn, workspace_id)
