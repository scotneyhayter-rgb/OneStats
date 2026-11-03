"""International match-index register endpoints (Part C).

Reads are available to match editors; registering entries and changing official status require
``match.manage``. Workspace-scoped (FORCE RLS) and audited by the domain layer. All counts returned
here are genuine (computed from rows); an unknown expected total is reported as null, never zero.
"""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain.intl import match_index

router = APIRouter(prefix="/workspaces/{workspace_id}/match-index", tags=["match-index"])

Ctx = Annotated[RequestContext, Depends(require_permission("match.manage"))]

_ERR = {
    "entry_not_found": status.HTTP_404_NOT_FOUND,
    "not_recognised_cannot_import": status.HTTP_409_CONFLICT,
    "cannot_verify_unimported": status.HTTP_409_CONFLICT,
    "expected_requires_multiple_sources": status.HTTP_422_UNPROCESSABLE_ENTITY,
}


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


def _err(exc: ValueError) -> HTTPException:
    return HTTPException(_ERR.get(str(exc), status.HTTP_400_BAD_REQUEST), str(exc))


class RegisterBody(BaseModel):
    format: str
    source_refs: dict[str, str] = Field(min_length=1)
    official_status: str = "recognised"
    match_number: int | None = None
    start_date: str | None = None
    date_precision: str = "exact"
    team_a: str | None = None
    team_b: str | None = None
    venue_name: str | None = None
    series: str | None = None
    confidence: float | None = None
    notes: str | None = None


class OfficialStatusBody(BaseModel):
    official_status: str
    reason: str | None = None


@router.get("")
def list_entries(workspace_id: UUID, settings: SettingsDep, ctx: Ctx,
                 format: str | None = None, state: str | None = None,
                 official_status: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    sql = f"SELECT {match_index._COLS} FROM match_index_entry WHERE workspace_id = :w"
    params: dict[str, Any] = {"w": workspace_id, "lim": min(limit, 1000)}
    if format:
        sql += " AND format = :f"; params["f"] = format
    if state:
        sql += " AND state = :st"; params["st"] = state
    if official_status:
        sql += " AND official_status = :os"; params["os"] = official_status
    sql += " ORDER BY start_date NULLS LAST, match_number NULLS LAST LIMIT :lim"
    from sqlalchemy import text
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


@router.get("/summary")
def summary(workspace_id: UUID, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return match_index.summary(conn, workspace_id)


@router.get("/coverage")
def coverage(workspace_id: UUID, settings: SettingsDep, ctx: Ctx, format: str, period: str = "all") -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        cov = match_index.get_coverage(conn, workspace_id, format, period)
        if cov is None:
            # unsearched scope: unknown is distinct from "searched, none found"
            return {"format": format, "period": period, "coverage_state": "unknown",
                    "expected_count": None, "indexed_count": 0, "imported_count": 0, "verified_count": 0}
        return cov


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(workspace_id: UUID, body: RegisterBody, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    actor = str(ctx.user["id"])
    try:
        with workspace_transaction(_engine(settings), workspace_id) as conn:
            return match_index.register(
                conn, workspace_id, actor, format=body.format, source_refs=body.source_refs,
                official_status=body.official_status, match_number=body.match_number,
                start_date=body.start_date, date_precision=body.date_precision, team_a=body.team_a,
                team_b=body.team_b, venue_name=body.venue_name, series=body.series,
                confidence=body.confidence, notes=body.notes)
    except ValueError as exc:
        raise _err(exc)


@router.post("/{entry_id}/official-status")
def set_official_status(workspace_id: UUID, entry_id: UUID, body: OfficialStatusBody,
                        settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    actor = str(ctx.user["id"])
    try:
        with workspace_transaction(_engine(settings), workspace_id) as conn:
            return match_index.set_official_status(conn, workspace_id, actor, entry_id,
                                                   body.official_status, reason=body.reason)
    except ValueError as exc:
        raise _err(exc)
