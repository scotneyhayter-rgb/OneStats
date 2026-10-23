"""Innings & extras endpoints (Phase 6, Stage 2).

Nested under a match. Workspace-scoped, gated by ``match.manage``, audited. Distinct totals,
optional official override (never overwrites source), and non-blocking validation.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import innings as innings_domain

router = APIRouter(prefix="/workspaces/{workspace_id}/matches/{match_id}/innings", tags=["innings"])

MatchCtx = Annotated[RequestContext, Depends(require_permission("match.manage"))]

_VALUE_ERR_STATUS = {
    "match_not_found": status.HTTP_404_NOT_FOUND,
    "innings_not_found": status.HTTP_404_NOT_FOUND,
    "team_not_in_match": status.HTTP_409_CONFLICT,
    "teams_must_differ": status.HTTP_409_CONFLICT,
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


class InningsCreate(BaseModel):
    inns_number: int = Field(ge=1)
    batting_team_id: UUID | None = None
    bowling_team_id: UUID | None = None
    status: str = "unknown"
    byes: int | None = Field(default=None, ge=0)
    legbyes: int | None = Field(default=None, ge=0)
    wides: int | None = Field(default=None, ge=0)
    noballs: int | None = Field(default=None, ge=0)
    penalty: int | None = Field(default=None, ge=0)
    iresult_raw: str | None = None
    notes: str | None = None
    source_system: str | None = None
    source_ref: str | None = None


class InningsUpdate(BaseModel):
    status: str | None = None
    batting_team_id: UUID | None = None
    bowling_team_id: UUID | None = None
    byes: int | None = Field(default=None, ge=0)
    legbyes: int | None = Field(default=None, ge=0)
    wides: int | None = Field(default=None, ge=0)
    noballs: int | None = Field(default=None, ge=0)
    penalty: int | None = Field(default=None, ge=0)
    iresult_raw: str | None = None
    notes: str | None = None


class OfficialOverride(BaseModel):
    total: int | None = Field(default=None, ge=0)
    wickets: int | None = Field(default=None, ge=0, le=10)
    reason: str | None = None
    evidence: str | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
def create_innings(workspace_id: UUID, match_id: UUID, body: InningsCreate, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            iid = innings_domain.create_innings(
                conn, workspace_id, str(ctx.user["id"]), match_id=match_id, **body.model_dump())
        except ValueError as exc:
            raise _value_error(exc) from exc
        return _ids(innings_domain.get_innings(conn, iid))


@router.get("")
def list_innings(workspace_id: UUID, match_id: UUID, settings: SettingsDep, ctx: MatchCtx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_ids(i) for i in innings_domain.list_innings(conn, match_id)]


@router.patch("/{innings_id}")
def update_innings(workspace_id: UUID, match_id: UUID, innings_id: UUID, body: InningsUpdate, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _ids(innings_domain.update_innings(conn, workspace_id, str(ctx.user["id"]), innings_id,
                                                      **body.model_dump(exclude_none=True)))
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.post("/{innings_id}/official-total")
def set_official_total(workspace_id: UUID, match_id: UUID, innings_id: UUID, body: OfficialOverride, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _ids(innings_domain.set_official_total(
                conn, workspace_id, str(ctx.user["id"]), innings_id, total=body.total, wickets=body.wickets,
                reason=body.reason, evidence=body.evidence))
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.get("/{innings_id}/totals")
def totals(workspace_id: UUID, match_id: UUID, innings_id: UUID, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return innings_domain.totals(conn, innings_id)
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.get("/{innings_id}/validate")
def validate(workspace_id: UUID, match_id: UUID, innings_id: UUID, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return {"warnings": innings_domain.validation_warnings(conn, innings_id)}
        except ValueError as exc:
            raise _value_error(exc) from exc
