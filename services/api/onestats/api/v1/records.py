"""Records, Rankings & Achievements API (Phase 13). Workspace-scoped, gated by ``match.view``.

Reads all-time record holders, seasonal leaders, career milestones and upcoming milestones from the
Records Engine (which composes the Phase 12 statistics engine — approved data only, nothing invented).
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain.records import milestones, records

router = APIRouter(prefix="/workspaces/{workspace_id}/records", tags=["records"])
ViewCtx = Annotated[RequestContext, Depends(require_permission("match.view"))]


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


def _filters(workspace_id: UUID, season_id: UUID | None, grade_id: UUID | None, competition_id: UUID | None,
             team_id: UUID | None, split: str | None, venue: str | None, format: str | None,
             date_from: date | None, date_to: date | None) -> dict[str, Any]:
    return {"workspace_id": workspace_id, "season_id": season_id, "grade_id": grade_id,
            "competition_id": competition_id, "team_id": team_id, "split": split, "venue": venue,
            "format": format, "date_from": date_from, "date_to": date_to}


@router.get("")
def all_time(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx, season_id: UUID | None = None,
             grade_id: UUID | None = None, competition_id: UUID | None = None, team_id: UUID | None = None,
             split: str | None = None, venue: str | None = None, top: int = 10) -> dict[str, Any]:
    f = _filters(workspace_id, season_id, grade_id, competition_id, team_id, split, venue, None, None, None)
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return records.all_time_records(conn, workspace_id, f, top=top)


@router.get("/seasonal")
def seasonal(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx, competition_id: UUID | None = None) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return records.seasonal_leaders(conn, workspace_id, competition_id=competition_id)


@router.get("/milestones/{person_id}")
def person_milestones(workspace_id: UUID, person_id: UUID, settings: SettingsDep, ctx: ViewCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return milestones.person_milestones(conn, workspace_id, person_id)


@router.get("/upcoming")
def upcoming(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx, window: int = 10) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return milestones.upcoming_for_workspace(conn, workspace_id, window=window)
