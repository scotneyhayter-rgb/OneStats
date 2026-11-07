"""Bowling endpoints (Phase 6, Stage 4).

Nested under an innings. Workspace-scoped, gated by ``match.manage``, audited. Overs are never
decimals — the original notation is kept in ``overs_text`` and the canonical ``legal_balls`` is
derived from the match's balls-per-over (or supplied directly). Recorded figures and the
calculated reconciliation are kept distinct; validation is non-blocking.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import bowling as bowling_domain
from onestats.domain import results

router = APIRouter(
    prefix="/workspaces/{workspace_id}/innings/{innings_id}/bowling", tags=["bowling"]
)

MatchCtx = Annotated[RequestContext, Depends(require_permission("match.manage"))]

_VALUE_ERR_STATUS = {
    "innings_not_found": status.HTTP_404_NOT_FOUND,
    "entry_not_found": status.HTTP_404_NOT_FOUND,
    "duplicate_bowler": status.HTTP_409_CONFLICT,
    "duplicate_order": status.HTTP_409_CONFLICT,
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


class BowlingCreate(BaseModel):
    person_id: UUID | None = None
    bowling_order: int | None = Field(default=None, ge=1)
    overs_text: str | None = None
    legal_balls: int | None = Field(default=None, ge=0)
    maidens: int | None = Field(default=None, ge=0)
    runs_conceded: int | None = Field(default=None, ge=0)
    wickets: int | None = Field(default=None, ge=0, le=10)
    wides: int | None = Field(default=None, ge=0)
    noballs: int | None = Field(default=None, ge=0)
    bowling_type_raw: str | None = None
    notes: str | None = None
    evidence: str | None = None
    source_system: str | None = None
    source_ref: str | None = None


class BowlingUpdate(BaseModel):
    person_id: UUID | None = None
    bowling_order: int | None = Field(default=None, ge=1)
    overs_text: str | None = None
    legal_balls: int | None = Field(default=None, ge=0)
    maidens: int | None = Field(default=None, ge=0)
    runs_conceded: int | None = Field(default=None, ge=0)
    wickets: int | None = Field(default=None, ge=0, le=10)
    wides: int | None = Field(default=None, ge=0)
    noballs: int | None = Field(default=None, ge=0)
    bowling_type_raw: str | None = None
    notes: str | None = None
    evidence: str | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
def create_entry(workspace_id: UUID, innings_id: UUID, body: BowlingCreate, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            eid = bowling_domain.create_entry(
                conn, workspace_id, str(ctx.user["id"]), innings_id=innings_id, **body.model_dump())
        except ValueError as exc:
            raise _value_error(exc) from exc
        results.recalc_for_innings(conn, workspace_id, str(ctx.user["id"]), innings_id)  # flag revision etc.
        return _ids(bowling_domain.get_entry(conn, eid))


@router.get("")
def list_entries(workspace_id: UUID, innings_id: UUID, settings: SettingsDep, ctx: MatchCtx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_ids(e) for e in bowling_domain.list_entries(conn, innings_id)]


@router.patch("/{entry_id}")
def update_entry(workspace_id: UUID, innings_id: UUID, entry_id: UUID, body: BowlingUpdate, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            # exclude_unset (not exclude_none): the grid PATCHes only the field it changed, so an
            # explicit null means "clear this field" (e.g. the ✕ next to a bowler) and must be sent
            # through — fields the client never touched stay absent and are left unchanged.
            out = _ids(bowling_domain.update_entry(conn, workspace_id, str(ctx.user["id"]), entry_id,
                                                   **body.model_dump(exclude_unset=True)))
        except ValueError as exc:
            raise _value_error(exc) from exc
        results.recalc_for_innings(conn, workspace_id, str(ctx.user["id"]), innings_id)
        return out


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(workspace_id: UUID, innings_id: UUID, entry_id: UUID, settings: SettingsDep, ctx: MatchCtx) -> None:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            bowling_domain.delete_entry(conn, workspace_id, str(ctx.user["id"]), entry_id)
        except ValueError as exc:
            raise _value_error(exc) from exc
        results.recalc_for_innings(conn, workspace_id, str(ctx.user["id"]), innings_id)


@router.get("/card")
def bowling_card(workspace_id: UUID, innings_id: UUID, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return bowling_domain.bowling_card(conn, innings_id)


@router.get("/validate")
def validate(workspace_id: UUID, innings_id: UUID, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return {"warnings": bowling_domain.validation_warnings(conn, innings_id)}
