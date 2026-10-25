"""Official statistics endpoints (Phase 7, Stage 7.8).

Read official player statistics from the approved-match ledger, and (admin) trigger a workspace
backfill that recomputes the ledger for every match. Workspace-scoped and audited. This is the
foundation the future statistics/records/milestones modules build on — not those modules themselves.
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import recalc
from onestats.domain.stats import engine, reconciliation

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


def _filters(workspace_id: UUID, season_id: UUID | None, grade_id: UUID | None, competition_id: UUID | None,
             team_id: UUID | None, split: str | None, venue: str | None, format: str | None,
             date_from: date | None, date_to: date | None) -> dict[str, Any]:
    return {"workspace_id": workspace_id, "season_id": season_id, "grade_id": grade_id,
            "competition_id": competition_id, "team_id": team_id, "split": split, "venue": venue,
            "format": format, "date_from": date_from, "date_to": date_to}


# One signature of shared report filters for every leaderboard (real filters over the one engine).
def _common(workspace_id: UUID, season_id: UUID | None = None, grade_id: UUID | None = None,
            competition_id: UUID | None = None, team_id: UUID | None = None, split: str | None = None,
            venue: str | None = None, format: str | None = None, date_from: date | None = None,
            date_to: date | None = None, order_by: str | None = None, limit: int = 100) -> dict[str, Any]:
    return {"f": _filters(workspace_id, season_id, grade_id, competition_id, team_id, split, venue, format,
                          date_from, date_to), "order_by": order_by, "limit": limit}


@router.get("/batting")
def batting(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx, season_id: UUID | None = None,
            grade_id: UUID | None = None, competition_id: UUID | None = None, team_id: UUID | None = None,
            split: str | None = None, venue: str | None = None, format: str | None = None,
            date_from: date | None = None, date_to: date | None = None, order_by: str = "runs",
            limit: int = 100, min_runs: int | None = None) -> list[dict[str, Any]]:
    c = _common(workspace_id, season_id, grade_id, competition_id, team_id, split, venue, format, date_from, date_to)
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return engine.batting_leaders(conn, c["f"], order_by=order_by, limit=limit, min_runs=min_runs)


@router.get("/bowling")
def bowling(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx, season_id: UUID | None = None,
            grade_id: UUID | None = None, competition_id: UUID | None = None, team_id: UUID | None = None,
            split: str | None = None, venue: str | None = None, format: str | None = None,
            date_from: date | None = None, date_to: date | None = None, order_by: str = "wickets",
            limit: int = 100, over_length: int = 6, min_wickets: int | None = None) -> list[dict[str, Any]]:
    c = _common(workspace_id, season_id, grade_id, competition_id, team_id, split, venue, format, date_from, date_to)
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return engine.bowling_leaders(conn, c["f"], order_by=order_by, limit=limit, over_length=over_length,
                                      min_wickets=min_wickets)


@router.get("/fielding")
def fielding(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx, season_id: UUID | None = None,
             grade_id: UUID | None = None, competition_id: UUID | None = None, team_id: UUID | None = None,
             split: str | None = None, venue: str | None = None, order_by: str = "catches",
             limit: int = 100) -> list[dict[str, Any]]:
    c = _common(workspace_id, season_id, grade_id, competition_id, team_id, split, venue, None, None, None)
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return engine.fielding_leaders(conn, c["f"], order_by=order_by, limit=limit)


@router.get("/captaincy")
def captaincy(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx, season_id: UUID | None = None,
              grade_id: UUID | None = None, competition_id: UUID | None = None, team_id: UUID | None = None,
              split: str | None = None, order_by: str = "captained", limit: int = 100,
              min_eligible: int = 20) -> list[dict[str, Any]]:
    c = _common(workspace_id, season_id, grade_id, competition_id, team_id, split, None, None, None, None)
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return engine.captaincy_leaders(conn, c["f"], order_by=order_by, limit=limit, min_eligible=min_eligible)


@router.get("/participation")
def participation(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx, season_id: UUID | None = None,
                  grade_id: UUID | None = None, competition_id: UUID | None = None, team_id: UUID | None = None,
                  split: str | None = None, order_by: str = "matches", limit: int = 100) -> list[dict[str, Any]]:
    c = _common(workspace_id, season_id, grade_id, competition_id, team_id, split, None, None, None, None)
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return engine.participation_leaders(conn, c["f"], order_by=order_by, limit=limit)


@router.get("/teams")
def teams(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx, season_id: UUID | None = None,
          grade_id: UUID | None = None, competition_id: UUID | None = None, split: str | None = None,
          order_by: str = "wins", limit: int = 100) -> list[dict[str, Any]]:
    c = _common(workspace_id, season_id, grade_id, competition_id, None, split, None, None, None, None)
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return engine.team_records(conn, c["f"], order_by=order_by, limit=limit)


@router.get("/matches/{match_id}/reconciliation")
def match_reconciliation(workspace_id: UUID, match_id: UUID, settings: SettingsDep, ctx: ViewCtx) -> dict[str, Any]:
    """Run-out reconciliation for a match's innings: recorded wickets vs dismissals, with a visible run
    outs count and warnings where the scorecard is incomplete (never an invented dismissal)."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return reconciliation.reconcile_match(conn, workspace_id, match_id)
