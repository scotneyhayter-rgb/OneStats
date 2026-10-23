"""Premiership endpoints (Phase 6, Stage 6).

Workspace-scoped, gated by ``competition.manage``, audited. A premiership is recorded explicitly —
never derived from a Grand Final result — with winning team(s) (shared supported), optional
runner-up, the deciding series/match, a verification status and evidence. Validation is
non-blocking.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import premierships as prem

router = APIRouter(prefix="/workspaces/{workspace_id}/premierships", tags=["premierships"])

CompCtx = Annotated[RequestContext, Depends(require_permission("competition.manage"))]

_VALUE_ERR_STATUS = {
    "premiership_not_found": status.HTTP_404_NOT_FOUND,
    "competition_not_found": status.HTTP_404_NOT_FOUND,
    "season_not_found": status.HTTP_404_NOT_FOUND,
    "grade_not_found": status.HTTP_404_NOT_FOUND,
    "series_not_found": status.HTTP_404_NOT_FOUND,
    "match_not_found": status.HTTP_404_NOT_FOUND,
    "team_not_found": status.HTTP_404_NOT_FOUND,
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


class PremiershipCreate(BaseModel):
    competition_id: UUID
    season_id: UUID | None = None
    grade_id: UUID | None = None
    outcome: str = Field(default="unknown", pattern="^(awarded|shared|abandoned|not_awarded|unknown)$")
    runner_up_team_id: UUID | None = None
    deciding_series_id: UUID | None = None
    deciding_match_id: UUID | None = None
    verification_status: str = Field(default="unverified", pattern="^(unverified|provisional|verified|disputed)$")
    evidence: str | None = None
    notes: str | None = None
    source_system: str | None = None
    source_ref: str | None = None


class PremiershipUpdate(BaseModel):
    season_id: UUID | None = None
    grade_id: UUID | None = None
    outcome: str | None = Field(default=None, pattern="^(awarded|shared|abandoned|not_awarded|unknown)$")
    runner_up_team_id: UUID | None = None
    deciding_series_id: UUID | None = None
    deciding_match_id: UUID | None = None
    verification_status: str | None = Field(default=None, pattern="^(unverified|provisional|verified|disputed)$")
    evidence: str | None = None
    notes: str | None = None


class WinnerAdd(BaseModel):
    team_id: UUID
    role: str = Field(default="winner", pattern="^(winner|shared_winner)$")


@router.post("", status_code=status.HTTP_201_CREATED)
def create_premiership(workspace_id: UUID, body: PremiershipCreate, settings: SettingsDep, ctx: CompCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            pid = prem.create_premiership(conn, workspace_id, str(ctx.user["id"]), **body.model_dump())
        except ValueError as exc:
            raise _value_error(exc) from exc
        return _ids(prem.detail(conn, pid))


@router.get("")
def list_premierships(workspace_id: UUID, settings: SettingsDep, ctx: CompCtx, competition_id: UUID | None = None) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_ids(p) for p in prem.list_premierships(conn, competition_id=competition_id)]


@router.get("/{premiership_id}")
def get_premiership(workspace_id: UUID, premiership_id: UUID, settings: SettingsDep, ctx: CompCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        d = prem.detail(conn, premiership_id)
        if d is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "premiership_not_found")
        d["winners"] = [_ids(w) for w in d["winners"]]
        return _ids(d)


@router.patch("/{premiership_id}")
def update_premiership(workspace_id: UUID, premiership_id: UUID, body: PremiershipUpdate, settings: SettingsDep, ctx: CompCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _ids(prem.update_premiership(conn, workspace_id, str(ctx.user["id"]), premiership_id,
                                                **body.model_dump(exclude_none=True)))
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.delete("/{premiership_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_premiership(workspace_id: UUID, premiership_id: UUID, settings: SettingsDep, ctx: CompCtx) -> None:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            prem.delete_premiership(conn, workspace_id, str(ctx.user["id"]), premiership_id)
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.post("/{premiership_id}/winners", status_code=status.HTTP_201_CREATED)
def add_winner(workspace_id: UUID, premiership_id: UUID, body: WinnerAdd, settings: SettingsDep, ctx: CompCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _ids(prem.add_winner(conn, workspace_id, str(ctx.user["id"]), premiership_id,
                                        body.team_id, role=body.role))
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.delete("/{premiership_id}/winners/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_winner(workspace_id: UUID, premiership_id: UUID, team_id: UUID, settings: SettingsDep, ctx: CompCtx) -> None:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            prem.remove_winner(conn, workspace_id, str(ctx.user["id"]), premiership_id, team_id)
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.get("/{premiership_id}/validate")
def validate(workspace_id: UUID, premiership_id: UUID, settings: SettingsDep, ctx: CompCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return {"warnings": prem.validation_warnings(conn, premiership_id)}
        except ValueError as exc:
            raise _value_error(exc) from exc
