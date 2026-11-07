"""Fall of wicket & partnership endpoints (Phase 6, Stage 5).

Nested under an innings. Workspace-scoped, gated by ``match.manage``, audited. Fall-of-wicket and
batting-partnership CRUD, a non-blocking validation endpoint, and a read-only building block for
the future bowling-partnership statistical report.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import matches
from onestats.domain import partnerships as pshp

router = APIRouter(prefix="/workspaces/{workspace_id}/innings/{innings_id}", tags=["partnerships"])

MatchCtx = Annotated[RequestContext, Depends(require_permission("match.manage"))]

_VALUE_ERR_STATUS = {
    "innings_not_found": status.HTTP_404_NOT_FOUND,
    "fow_not_found": status.HTTP_404_NOT_FOUND,
    "partnership_not_found": status.HTTP_404_NOT_FOUND,
    "duplicate_wicket_number": status.HTTP_409_CONFLICT,
    "players_must_differ": status.HTTP_409_CONFLICT,
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


class FowCreate(BaseModel):
    wicket_number: int | None = Field(default=None, ge=1)
    team_score: int | None = Field(default=None, ge=0)
    dismissed_person_id: UUID | None = None
    not_out_person_id: UUID | None = None
    batting_entry_id: UUID | None = None
    overs_text: str | None = None
    legal_balls: int | None = Field(default=None, ge=0)
    notes: str | None = None
    evidence: str | None = None
    source_system: str | None = None
    source_ref: str | None = None


class FowUpdate(BaseModel):
    wicket_number: int | None = Field(default=None, ge=1)
    team_score: int | None = Field(default=None, ge=0)
    dismissed_person_id: UUID | None = None
    not_out_person_id: UUID | None = None
    batting_entry_id: UUID | None = None
    overs_text: str | None = None
    legal_balls: int | None = Field(default=None, ge=0)
    notes: str | None = None
    evidence: str | None = None


_ORIGIN = "^(calculated|manual|verified|unknown)$"


class _Contrib(BaseModel):
    runs_b1: int | None = Field(default=None, ge=0)
    runs_b2: int | None = Field(default=None, ge=0)
    extras: int | None = Field(default=None, ge=0)
    balls_b1: int | None = Field(default=None, ge=0)
    balls_b2: int | None = Field(default=None, ge=0)
    balls_total: int | None = Field(default=None, ge=0)
    fours_b1: int | None = Field(default=None, ge=0)
    sixes_b1: int | None = Field(default=None, ge=0)
    fours_b2: int | None = Field(default=None, ge=0)
    sixes_b2: int | None = Field(default=None, ge=0)
    confidence: str | None = None


class PartnershipCreate(_Contrib):
    wicket_number: int | None = Field(default=None, ge=1)
    runs: int | None = Field(default=None, ge=0)
    balls: int | None = Field(default=None, ge=0)
    player1_person_id: UUID | None = None
    player2_person_id: UUID | None = None
    unbroken: bool | None = None
    end_reason: str | None = None
    origin: str = Field(default="manual", pattern=_ORIGIN)
    notes: str | None = None
    evidence: str | None = None
    source_system: str | None = None
    source_ref: str | None = None


class PartnershipUpdate(_Contrib):
    wicket_number: int | None = Field(default=None, ge=1)
    runs: int | None = Field(default=None, ge=0)
    balls: int | None = Field(default=None, ge=0)
    player1_person_id: UUID | None = None
    player2_person_id: UUID | None = None
    unbroken: bool | None = None
    end_reason: str | None = None
    origin: str | None = Field(default=None, pattern=_ORIGIN)
    notes: str | None = None
    evidence: str | None = None


# ----- fall of wicket -------------------------------------------------------------------------

def _auto_derive(conn: Any, workspace_id: UUID, actor: str, innings_id: UUID) -> None:
    """Re-derive this innings' CALCULATED partnerships automatically (Phase 7.2) whenever its fall
    of wickets change — no manual button. Idempotent; manual/verified partnerships are preserved;
    a derivation that cannot proceed is non-blocking (the FOW change still saves). Also flags an
    approved scorecard as revised (Stage 7.1) so official stats keep the last approved version."""
    try:
        pshp.derive_from_fow(conn, workspace_id, actor, innings_id)
    except ValueError:
        pass
    mid = conn.execute(text("SELECT match_id FROM innings WHERE id = :i"), {"i": innings_id}).scalar_one_or_none()
    if mid is not None:
        matches.mark_revised_if_approved(conn, mid)


@router.post("/fall-of-wicket", status_code=status.HTTP_201_CREATED)
def create_fow(workspace_id: UUID, innings_id: UUID, body: FowCreate, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            fid = pshp.create_fow(conn, workspace_id, str(ctx.user["id"]), innings_id=innings_id, **body.model_dump())
        except ValueError as exc:
            raise _value_error(exc) from exc
        _auto_derive(conn, workspace_id, str(ctx.user["id"]), innings_id)
        return _ids(pshp.get_fow(conn, fid))


@router.get("/fall-of-wicket")
def list_fow(workspace_id: UUID, innings_id: UUID, settings: SettingsDep, ctx: MatchCtx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_ids(f) for f in pshp.list_fow(conn, innings_id)]


@router.patch("/fall-of-wicket/{fow_id}")
def update_fow(workspace_id: UUID, innings_id: UUID, fow_id: UUID, body: FowUpdate, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            # exclude_unset (not exclude_none): an explicit null clears that field (e.g. the ✕ next to
            # the dismissed batter); untouched fields stay absent and are left unchanged.
            updated = _ids(pshp.update_fow(conn, workspace_id, str(ctx.user["id"]), fow_id,
                                           **body.model_dump(exclude_unset=True)))
        except ValueError as exc:
            raise _value_error(exc) from exc
        _auto_derive(conn, workspace_id, str(ctx.user["id"]), innings_id)
        return updated


@router.delete("/fall-of-wicket/{fow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fow(workspace_id: UUID, innings_id: UUID, fow_id: UUID, settings: SettingsDep, ctx: MatchCtx) -> None:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            pshp.delete_fow(conn, workspace_id, str(ctx.user["id"]), fow_id)
        except ValueError as exc:
            raise _value_error(exc) from exc
        _auto_derive(conn, workspace_id, str(ctx.user["id"]), innings_id)


# ----- partnerships ---------------------------------------------------------------------------

@router.post("/partnerships", status_code=status.HTTP_201_CREATED)
def create_partnership(workspace_id: UUID, innings_id: UUID, body: PartnershipCreate, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            pid = pshp.create_partnership(conn, workspace_id, str(ctx.user["id"]), innings_id=innings_id, **body.model_dump())
        except ValueError as exc:
            raise _value_error(exc) from exc
        return _ids(pshp.get_partnership(conn, pid))


@router.get("/partnerships")
def list_partnerships(workspace_id: UUID, innings_id: UUID, settings: SettingsDep, ctx: MatchCtx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_ids(p) for p in pshp.list_partnerships(conn, innings_id)]


@router.patch("/partnerships/{partnership_id}")
def update_partnership(workspace_id: UUID, innings_id: UUID, partnership_id: UUID, body: PartnershipUpdate, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            # exclude_unset (not exclude_none): an explicit null clears that field (e.g. the ✕ next to
            # a partnership batter); untouched fields stay absent and are left unchanged.
            return _ids(pshp.update_partnership(conn, workspace_id, str(ctx.user["id"]), partnership_id,
                                                **body.model_dump(exclude_unset=True)))
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.delete("/partnerships/{partnership_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_partnership(workspace_id: UUID, innings_id: UUID, partnership_id: UUID, settings: SettingsDep, ctx: MatchCtx) -> None:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            pshp.delete_partnership(conn, workspace_id, str(ctx.user["id"]), partnership_id)
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.post("/partnerships/derive")
def derive_partnerships(workspace_id: UUID, innings_id: UUID, settings: SettingsDep, ctx: MatchCtx) -> list[dict[str, Any]]:
    """Regenerate calculated partnerships from Fall of Wickets (manual/verified rows preserved)."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return [_ids(p) for p in pshp.derive_from_fow(conn, workspace_id, str(ctx.user["id"]), innings_id)]
        except ValueError as exc:
            raise _value_error(exc) from exc


# ----- reconciliation & bowling-partnership building block ------------------------------------

@router.get("/partnerships-validate")
def validate(workspace_id: UUID, innings_id: UUID, settings: SettingsDep, ctx: MatchCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return {"warnings": pshp.validation_warnings(conn, innings_id)}


@router.get("/bowling-partnership-inputs")
def bowling_partnership_inputs(workspace_id: UUID, innings_id: UUID, settings: SettingsDep, ctx: MatchCtx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_ids(r) for r in pshp.bowling_partnership_inputs(conn, innings_id)]
