"""Participation & attribution endpoints (Phase 6 foundation).

Read-only. Serves the scorecard Player Wizard (team/season roster suggestions) and the
foundations of player/team attribution that the Phase 12 statistics engine will build on.
Workspace-scoped, gated by ``match.manage`` (the scorecard's permission), audited by nature of
being read-only (no writes here).
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import participation

router = APIRouter(prefix="/workspaces/{workspace_id}/participation", tags=["participation"])

Ctx = Annotated[RequestContext, Depends(require_permission("match.manage"))]


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


def _ids(d: dict[str, Any]) -> dict[str, Any]:
    return {k: (str(v) if isinstance(v, UUID) else v) for k, v in d.items()}


@router.get("/team-players")
def team_players(workspace_id: UUID, team_id: UUID, settings: SettingsDep, ctx: Ctx, season_id: UUID | None = None) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return [_ids(r) for r in participation.team_season_players(conn, team_id, season_id)]
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/appearances")
def appearances(workspace_id: UUID, person_id: UUID, settings: SettingsDep, ctx: Ctx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_ids(r) for r in participation.player_appearances(conn, person_id)]


@router.get("/career")
def career(workspace_id: UUID, person_id: UUID, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return participation.player_career_totals(conn, person_id)


@router.get("/team-totals")
def team_totals(workspace_id: UUID, team_id: UUID, settings: SettingsDep, ctx: Ctx, season_id: UUID | None = None) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return participation.team_totals(conn, team_id, season_id)
