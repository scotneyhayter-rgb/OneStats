"""Format-aware international statistics endpoints (Part H).

Read-only views over the approved-statistics ledger, partitioned by the three recognised men's
international formats (Test / ODI / T20I). They reuse the statistics engine's calculators and filters,
so every figure is genuine and unknown-aware; nothing here is computed independently. Available to any
workspace member who can view matches (``match.view``); workspace-scoped (FORCE RLS).
"""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain.intl import stats as intl_stats

router = APIRouter(prefix="/workspaces/{workspace_id}/intl-stats", tags=["intl-stats"])

Ctx = Annotated[RequestContext, Depends(require_permission("match.view"))]


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


@router.get("/formats")
def formats(workspace_id: UUID, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    """The recognised international formats and the disciplines a leaderboard can be built for."""
    return {"formats": list(intl_stats.INTL_FORMATS), "disciplines": list(intl_stats.DISCIPLINES)}


@router.get("/career/{person_id}")
def career(workspace_id: UUID, person_id: UUID, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    """A player's international career split by format (Test / ODI / T20I) plus an all-internationals
    line. Each format is a self-contained set of batting/bowling/fielding/participation/captaincy
    aggregates; format lines are reported separately, never pooled."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return intl_stats.format_career(conn, workspace_id, person_id)


@router.get("/leaders/{fmt}/{discipline}")
def leaders(workspace_id: UUID, fmt: str, discipline: str, settings: SettingsDep, ctx: Ctx,
            limit: int = 100, order_by: str | None = None,
            season_id: UUID | None = None, team_id: UUID | None = None,
            opposition_team_id: UUID | None = None, venue_id: UUID | None = None,
            date_from: str | None = None, date_to: str | None = None) -> list[dict[str, Any]]:
    """A single-format leaderboard for one discipline, with the engine's universal filters."""
    extra = {"season_id": season_id, "team_id": team_id, "opposition_team_id": opposition_team_id,
             "venue_id": venue_id, "date_from": date_from, "date_to": date_to}
    try:
        with workspace_transaction(_engine(settings), workspace_id) as conn:
            return intl_stats.format_leaders(conn, workspace_id, fmt, discipline,
                                             limit=min(limit, 500), order_by=order_by, filters=extra)
    except ValueError as exc:
        code = status.HTTP_404_NOT_FOUND if str(exc) in ("invalid_format", "invalid_discipline") \
            else status.HTTP_400_BAD_REQUEST
        raise HTTPException(code, str(exc))
