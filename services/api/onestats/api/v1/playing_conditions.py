"""Playing-conditions endpoints (Phase 4, Stage 4).

Workspace-scoped and gated by the ``competition.manage`` permission; mutations are audited.
Conditions are configured per competition/season/grade/match and resolved in priority order
match → grade → season → competition. Unknown values stay unknown (never defaulted).
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import playing_conditions

router = APIRouter(prefix="/workspaces/{workspace_id}/playing-conditions", tags=["playing-conditions"])

PCCtx = Annotated[RequestContext, Depends(require_permission("competition.manage"))]

_VALUE_ERR_STATUS = {
    "competition_not_found": status.HTTP_404_NOT_FOUND,
    "season_not_found": status.HTTP_404_NOT_FOUND,
    "grade_not_found": status.HTTP_404_NOT_FOUND,
    "invalid_scope": status.HTTP_400_BAD_REQUEST,
}


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


def _value_error(exc: ValueError) -> HTTPException:
    code = str(exc)
    return HTTPException(_VALUE_ERR_STATUS.get(code, status.HTTP_400_BAD_REQUEST), code)


class ConditionSet(BaseModel):
    scope: str = Field(pattern="^(competition|season|grade|match)$")
    target_id: UUID
    overs_limit: int | None = Field(default=None, gt=0)
    max_players: int | None = Field(default=None, gt=0)
    balls_per_over: int | None = Field(default=None, gt=0)
    innings_per_side: int | None = Field(default=None, gt=0)
    format: str | None = Field(default=None, max_length=100)
    points: dict[str, Any] | None = None
    extra: dict[str, Any] | None = None
    notes: str | None = None
    source_system: str | None = None
    source_ref: str | None = None


@router.put("", status_code=status.HTTP_200_OK)
def set_conditions(workspace_id: UUID, body: ConditionSet, settings: SettingsDep, ctx: PCCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return playing_conditions.set_conditions(
                conn, workspace_id, str(ctx.user["id"]), scope=body.scope, target_id=body.target_id,
                overs_limit=body.overs_limit, max_players=body.max_players,
                balls_per_over=body.balls_per_over, innings_per_side=body.innings_per_side,
                format=body.format, points=body.points, extra=body.extra, notes=body.notes,
                source_system=body.source_system, source_ref=body.source_ref,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.get("")
def list_conditions(
    workspace_id: UUID, settings: SettingsDep, ctx: PCCtx, competition_id: UUID | None = None
) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return playing_conditions.list_conditions(conn, competition_id=competition_id)


@router.get("/resolve")
def resolve(
    workspace_id: UUID, settings: SettingsDep, ctx: PCCtx,
    competition_id: UUID | None = None, season_id: UUID | None = None,
    grade_id: UUID | None = None, match_id: UUID | None = None,
) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return playing_conditions.resolve_effective(
            conn, competition_id=competition_id, season_id=season_id,
            grade_id=grade_id, match_id=match_id,
        )


@router.get("/{scope}/{target_id}")
def get_for_scope(workspace_id: UUID, scope: str, target_id: UUID, settings: SettingsDep, ctx: PCCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            row = playing_conditions.get_for_scope(conn, scope, target_id)
        except ValueError as exc:
            raise _value_error(exc) from exc
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "playing_condition_not_found")
        return row


@router.delete("/{scope}/{target_id}", status_code=status.HTTP_200_OK)
def clear_conditions(workspace_id: UUID, scope: str, target_id: UUID, settings: SettingsDep, ctx: PCCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            removed = playing_conditions.clear_conditions(conn, workspace_id, str(ctx.user["id"]), scope=scope, target_id=target_id)
        except ValueError as exc:
            raise _value_error(exc) from exc
        return {"removed": removed}
