"""Finals Series endpoints (Phase 4, Stage 6 — revised).

Workspace-scoped, gated by ``competition.manage``, audited. Provides the series/team/game
foundation and outcome. Match-level statistics (appearances, premiership counting) depend on the
canonical match model and are deferred to Phase 8.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import finals_series

router = APIRouter(prefix="/workspaces/{workspace_id}/finals-series", tags=["finals-series"])

FSCtx = Annotated[RequestContext, Depends(require_permission("competition.manage"))]

_VALUE_ERR_STATUS = {
    "series_not_found": status.HTTP_404_NOT_FOUND,
    "competition_not_found": status.HTTP_404_NOT_FOUND,
    "team_not_found": status.HTTP_404_NOT_FOUND,
    "invalid_format": status.HTTP_400_BAD_REQUEST,
    "invalid_outcome": status.HTTP_400_BAD_REQUEST,
    "winner_not_participant": status.HTTP_409_CONFLICT,
    "invalid_game_number": status.HTTP_400_BAD_REQUEST,
}


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


def _value_error(exc: ValueError) -> HTTPException:
    return HTTPException(_VALUE_ERR_STATUS.get(str(exc), status.HTTP_400_BAD_REQUEST), str(exc))


def _ids(d: dict[str, Any]) -> dict[str, Any]:
    return {k: (str(v) if isinstance(v, UUID) else v) for k, v in d.items()}


class SeriesCreate(BaseModel):
    competition_id: UUID
    name: str = Field(min_length=1, max_length=200)
    format: str = Field(default="single", pattern="^(single|best_of_3|best_of_5|custom)$")
    season_id: UUID | None = None
    grade_id: UUID | None = None
    is_grand_final_series: bool = False
    rules: dict[str, Any] | None = None
    evidence: str | None = None
    source_system: str | None = None
    source_ref: str | None = None


class TeamAdd(BaseModel):
    team_id: UUID
    seed_label: str | None = None


class GameAdd(BaseModel):
    game_number: int = Field(ge=1)
    match_id: UUID | None = None
    match_source_ref: str | None = None
    notes: str | None = None


class OutcomeSet(BaseModel):
    outcome: str = Field(pattern="^(in_progress|decided|drawn|tied|incomplete|abandoned|unresolved)$")
    winner_team_id: UUID | None = None
    outcome_notes: str | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
def create_series(workspace_id: UUID, body: SeriesCreate, settings: SettingsDep, ctx: FSCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            sid = finals_series.create_series(
                conn, workspace_id, str(ctx.user["id"]), competition_id=body.competition_id,
                name=body.name, format=body.format, season_id=body.season_id, grade_id=body.grade_id,
                is_grand_final_series=body.is_grand_final_series, rules=body.rules,
                evidence=body.evidence, source_system=body.source_system, source_ref=body.source_ref,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return _ids(finals_series.get_series(conn, sid))


@router.get("")
def list_series(workspace_id: UUID, settings: SettingsDep, ctx: FSCtx, competition_id: UUID | None = None) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_ids(s) for s in finals_series.list_series(conn, competition_id=competition_id)]


@router.get("/{series_id}")
def get_series(workspace_id: UUID, series_id: UUID, settings: SettingsDep, ctx: FSCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        d = finals_series.detail(conn, series_id)
        if d is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "series_not_found")
        d["teams"] = [_ids(t) for t in d["teams"]]
        d["games"] = [_ids(g) for g in d["games"]]
        return _ids(d)


@router.post("/{series_id}/teams", status_code=status.HTTP_201_CREATED)
def add_team(workspace_id: UUID, series_id: UUID, body: TeamAdd, settings: SettingsDep, ctx: FSCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _ids(finals_series.add_team(conn, workspace_id, str(ctx.user["id"]), series_id, body.team_id, seed_label=body.seed_label))
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.post("/{series_id}/games", status_code=status.HTTP_201_CREATED)
def add_game(workspace_id: UUID, series_id: UUID, body: GameAdd, settings: SettingsDep, ctx: FSCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _ids(finals_series.add_game(
                conn, workspace_id, str(ctx.user["id"]), series_id, game_number=body.game_number,
                match_id=body.match_id, match_source_ref=body.match_source_ref, notes=body.notes,
            ))
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.patch("/{series_id}/outcome")
def set_outcome(workspace_id: UUID, series_id: UUID, body: OutcomeSet, settings: SettingsDep, ctx: FSCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _ids(finals_series.set_outcome(
                conn, workspace_id, str(ctx.user["id"]), series_id,
                outcome=body.outcome, winner_team_id=body.winner_team_id, outcome_notes=body.outcome_notes,
            ))
        except ValueError as exc:
            raise _value_error(exc) from exc
