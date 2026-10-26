"""Authenticated member portal (Phase 16 follow-up) — workspace-scoped, read-only.

A permission-scoped read-only surface for **members** (``match.view``): the club's public published items
plus the non-public catalogue they are allowed to see, and a pointer to the read-only **Ask OneStats**
surface (the existing deterministic Ask endpoint) when the member may use it. This is the authenticated
counterpart to the public ``/public/club/{id}`` portal; it needs no hosting decision and works today.
"""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import publishing

router = APIRouter(prefix="/workspaces/{workspace_id}/portal", tags=["portal"])
MemberCtx = Annotated[RequestContext, Depends(require_permission("match.view"))]


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


@router.get("")
def member_portal(workspace_id: UUID, settings: SettingsDep, ctx: MemberCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        out = publishing.member_portal(conn, workspace_id)
    # Ask-on-portal: expose the read-only Ask surface to members who may query it
    ask_enabled = "ask.query" in ctx.permissions
    out["ask"] = {"enabled": ask_enabled,
                  "endpoint": f"/api/v1/workspaces/{workspace_id}/ask" if ask_enabled else None}
    return out
