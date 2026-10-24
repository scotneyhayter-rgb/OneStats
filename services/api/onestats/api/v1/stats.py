"""Official statistics endpoints (Phase 7, Stage 7.8).

Read official player statistics from the approved-match ledger, and (admin) trigger a workspace
backfill that recomputes the ledger for every match. Workspace-scoped and audited. This is the
foundation the future statistics/records/milestones modules build on — not those modules themselves.
"""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import recalc

router = APIRouter(prefix="/workspaces/{workspace_id}/stats", tags=["stats"])

ViewCtx = Annotated[RequestContext, Depends(require_permission("match.view"))]
AdminCtx = Annotated[RequestContext, Depends(require_permission("workspace.manage"))]


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


@router.get("/people/{person_id}")
def official_person_stats(workspace_id: UUID, person_id: UUID, settings: SettingsDep, ctx: ViewCtx) -> dict[str, Any]:
    """Official career batting and bowling for a person, from approved scorecards only (merge-aware)."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return {
            "person_id": str(person_id),
            "batting": recalc.official_player_batting(conn, workspace_id, person_id),
            "bowling": recalc.official_player_bowling(conn, workspace_id, person_id),
        }


@router.post("/recalc")
def recalc_backfill(workspace_id: UUID, settings: SettingsDep, ctx: AdminCtx) -> dict[str, Any]:
    """Recompute the official-statistics ledger for every match in the workspace. Idempotent."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return recalc.backfill(conn, workspace_id, str(ctx.user["id"]))
