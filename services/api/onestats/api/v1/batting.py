"""Batting & dismissal endpoints (Phase 6, Stage 3).

Nested under an innings. Workspace-scoped, gated by ``match.manage``, audited. The mapped
dismissal type is stored next to the preserved original source code; non-blocking validation
surfaces inconsistencies without rejecting legitimate incomplete historical cards.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import batting as batting_domain

router = APIRouter(
    prefix="/workspaces/{workspace_id}/innings/{innings_id}/batting", tags=["batting"]
)

MatchCtx = Annotated[RequestContext, Depends(require_permission("match.manage"))]

_VALUE_ERR_STATUS = {
    "innings_not_found": status.HTTP_404_NOT_FOUND,
    "entry_not_found": status.HTTP_404_NOT_FOUND,
    "duplicate_batter": status.HTTP_409_CONFLICT,
    "duplicate_position": status.HTTP_409_CONFLICT,
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


class BattingCreate(BaseModel):
    person_id: UUID | None = None
    batting_position: int | None = Field(default=None, ge=1)
    runs: int | None = Field(default=None, ge=0)
    balls_faced: int | None = Field(default=None, ge=0)
    fours: int | None = Field(default=None, ge=0)
    sixes: int | None = Field(default=None, ge=0)
    minutes: int | None = Field(default=None, ge=0)
    dismissal_type: str | None = None
    dismissal_source_code: str | None = None
    bowler_person_id: UUID | None = None
    fielder_person_id: UUID | None = None
    notes: str | None = None
    evidence: str | None = None
    source_system: str | None = None
    source_ref: str | None = None


class BattingUpdate(BaseModel):
    person_id: UUID | None = None
    batting_position: int | None = Field(default=None, ge=1)
    runs: int | None = Field(default=None, ge=0)
    balls_faced: int | None = Field(default=None, ge=0)
    fours: int | None = Field(default=None, ge=0)
    sixes: int | None = Field(default=None, ge=0)
    minutes: int | None = Field(default=None, ge=0)
    dismissal_type: str | None = None
    dismissal_source_code: str | None = None
    bowler_person_id: UUID | None = None
    fielder_person_id: UUID | None = None
    notes: str | None = None
    evidence: str | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
def create_entry(workspace_id: UUID, innings_id: UUID, body: BattingCreate, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            eid = batting_domain.create_entry(
                conn, workspace_id, str(ctx.user["id"]), innings_id=innings_id, **body.model_dump())
        except ValueError as exc:
            raise _value_error(exc) from exc
        return _ids(batting_domain.get_entry(conn, eid))


@router.get("")
def list_entries(workspace_id: UUID, innings_id: UUID, settings: SettingsDep, ctx: MatchCtx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_ids(e) for e in batting_domain.list_entries(conn, innings_id)]


@router.patch("/{entry_id}")
def update_entry(workspace_id: UUID, innings_id: UUID, entry_id: UUID, body: BattingUpdate, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _ids(batting_domain.update_entry(conn, workspace_id, str(ctx.user["id"]), entry_id,
                                                    **body.model_dump(exclude_none=True)))
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(workspace_id: UUID, innings_id: UUID, entry_id: UUID, settings: SettingsDep, ctx: MatchCtx) -> None:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            batting_domain.delete_entry(conn, workspace_id, str(ctx.user["id"]), entry_id)
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.get("/card")
def batting_card(workspace_id: UUID, innings_id: UUID, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return batting_domain.batting_card(conn, innings_id)


@router.get("/validate")
def validate(workspace_id: UUID, innings_id: UUID, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return {"warnings": batting_domain.validation_warnings(conn, innings_id)}
