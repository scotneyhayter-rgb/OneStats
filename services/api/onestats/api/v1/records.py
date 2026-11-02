"""Records, Rankings & Achievements API (Phase 13). Workspace-scoped, gated by ``match.view``.

Reads all-time record holders, seasonal leaders, career milestones and upcoming milestones from the
Records Engine (which composes the Phase 12 statistics engine — approved data only, nothing invented).
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain.records import badges, honours, milestones, records
from onestats.reports import record_book

router = APIRouter(prefix="/workspaces/{workspace_id}/records", tags=["records"])
ViewCtx = Annotated[RequestContext, Depends(require_permission("match.view"))]
HonourCtx = Annotated[RequestContext, Depends(require_permission("honour.manage"))]

_ERRORS = {
    "invalid_honour_type": status.HTTP_400_BAD_REQUEST,
    "title_required": status.HTTP_400_BAD_REQUEST,
    "honour_not_found": status.HTTP_404_NOT_FOUND,
    "invalid_status": status.HTTP_400_BAD_REQUEST,
}


def _s(d: dict[str, Any]) -> dict[str, Any]:
    return {k: (str(v) if isinstance(v, UUID) else v) for k, v in d.items()}


def _err(exc: ValueError) -> HTTPException:
    return HTTPException(_ERRORS.get(str(exc), status.HTTP_400_BAD_REQUEST), str(exc))


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
             split: str | None = None, venue: str | None = None, top: int = 10,
             club_mode: str = "primary", organisation_id: UUID | None = None) -> dict[str, Any]:
    # club_mode: 'primary' = each holder's main club; 'global' = every club they represented.
    # organisation_id: the "club lens" — restrict records to performances for that club's teams.
    mode = club_mode if club_mode in ("primary", "global") else "primary"
    f = _filters(workspace_id, season_id, grade_id, competition_id, team_id, split, venue, None, None, None)
    if organisation_id:
        f["organisation_id"] = organisation_id
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return records.all_time_records(conn, workspace_id, f, top=top, club_mode=mode)


@router.get("/partnerships/by-wicket")
def partnerships_by_wicket(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx,
                           season_id: UUID | None = None, competition_id: UUID | None = None,
                           organisation_id: UUID | None = None) -> list[dict[str, Any]]:
    """Record (highest) batting partnership for each wicket 1–10, optionally scoped to one club."""
    from onestats.domain.stats import records_detail
    f: dict[str, Any] = {"workspace_id": workspace_id, "season_id": season_id,
                         "competition_id": competition_id}
    if organisation_id:
        f["organisation_id"] = organisation_id
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return records_detail.highest_partnership_by_wicket(conn, f)


@router.get("/seasonal")
def seasonal(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx, competition_id: UUID | None = None) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return records.seasonal_leaders(conn, workspace_id, competition_id=competition_id)


@router.get("/milestones/{person_id}")
def person_milestones(workspace_id: UUID, person_id: UUID, settings: SettingsDep, ctx: ViewCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return milestones.person_milestones(conn, workspace_id, person_id)


@router.get("/upcoming")
def upcoming(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx, window: int | None = None,
             organisation_id: UUID | None = None) -> list[dict[str, Any]]:
    # window omitted → per-metric defaults (runs 50, wickets 10, matches 10); a value overrides all.
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return milestones.upcoming_for_workspace(conn, workspace_id, window=window,
                                                 organisation_id=organisation_id)


@router.get("/book/pdf")
def record_book_export(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx, sections: str | None = None,
                       competition_id: UUID | None = None, season_id: UUID | None = None) -> Response:
    """Club Record Book as a professional multi-section PDF (shared framework; cover page + numbering)."""
    secs = sections.split(",") if sections else None
    filters = {k: v for k, v in {"competition_id": competition_id, "season_id": season_id}.items() if v}
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        pdf = record_book.record_book_pdf(conn, settings, workspace_id, sections=secs, filters=filters)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="club-record-book.pdf"'})


@router.get("/badges/{person_id}")
def person_badges(workspace_id: UUID, person_id: UUID, settings: SettingsDep, ctx: ViewCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return badges.person_badges(conn, workspace_id, person_id)


class HonourCreate(BaseModel):
    honour_type: str = Field(pattern="^(life_member|honorary_member|club_award|historical_figure|other)$")
    title: str
    person_id: UUID | None = None
    award_category: str | None = None   # free-form (Best & Fairest, Batting Award, custom, ...)
    awarded_date: date | None = None
    awarded_season: str | None = None
    awarding_organisation_id: UUID | None = None
    description: str | None = None
    evidence: str | None = None
    media_asset_id: UUID | None = None
    notes: str | None = None
    status: str = Field(default="confirmed", pattern="^(proposed|confirmed)$")


class HonourUpdate(BaseModel):
    title: str | None = None
    award_category: str | None = None
    description: str | None = None
    evidence: str | None = None
    notes: str | None = None
    media_asset_id: UUID | None = None
    status: str | None = Field(default=None, pattern="^(proposed|confirmed)$")


@router.get("/honours")
def list_honours(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx, honour_type: str | None = None,
                 person_id: UUID | None = None) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_s(r) for r in honours.list_honours(conn, workspace_id, honour_type=honour_type, person_id=person_id)]


@router.post("/honours", status_code=status.HTTP_201_CREATED)
def create_honour(workspace_id: UUID, body: HonourCreate, settings: SettingsDep, ctx: HonourCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(honours.create_honour(conn, workspace_id, str(ctx.user["id"]), **body.model_dump()))
        except ValueError as exc:
            raise _err(exc) from exc


@router.patch("/honours/{honour_id}")
def update_honour(workspace_id: UUID, honour_id: UUID, body: HonourUpdate, settings: SettingsDep,
                  ctx: HonourCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(honours.update_honour(conn, workspace_id, str(ctx.user["id"]), honour_id,
                                            **body.model_dump(exclude_none=True)))
        except ValueError as exc:
            raise _err(exc) from exc
