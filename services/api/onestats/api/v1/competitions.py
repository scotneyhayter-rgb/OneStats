"""Competition structure endpoints (Phase 4, Stage 3).

Workspace-scoped and gated by the ``competition.manage`` permission; every mutation is audited by
the domain layer. Covers competitions (optional association ownership), divisions, grades (with
historical names), seasons (two-calendar-year labels, unknown-aware dates), team-grade-season
entries (idempotent), and the preparatory, unknown-aware match-classification vocabulary.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from onestats.api.deps import RequestContext, SettingsDep, require_any_permission, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import competitions, seasons

router = APIRouter(prefix="/workspaces/{workspace_id}/competitions", tags=["competitions"])

CompCtx = Annotated[RequestContext, Depends(require_permission("competition.manage"))]
# Reading the competition list is needed by the scorecard-entry/approval screens, so holders of
# match.manage / scorecard.approve may read it even without competition.manage. Writes stay gated above.
CompReadCtx = Annotated[RequestContext, Depends(
    require_any_permission("competition.manage", "match.manage", "scorecard.approve"))]

_VALUE_ERR_STATUS = {
    "competition_not_found": status.HTTP_404_NOT_FOUND,
    "association_not_found": status.HTTP_404_NOT_FOUND,
    "division_not_found": status.HTTP_404_NOT_FOUND,
    "grade_not_found": status.HTTP_404_NOT_FOUND,
    "season_not_found": status.HTTP_404_NOT_FOUND,
    "team_not_found": status.HTTP_404_NOT_FOUND,
    "duplicate_season": status.HTTP_409_CONFLICT,
    "grade_season_competition_mismatch": status.HTTP_409_CONFLICT,
}


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


def _value_error(exc: ValueError) -> HTTPException:
    code = str(exc)
    return HTTPException(_VALUE_ERR_STATUS.get(code, status.HTTP_400_BAD_REQUEST), code)


def _str_uuids(d: dict[str, Any]) -> dict[str, Any]:
    return {k: (str(v) if isinstance(v, UUID) else v) for k, v in d.items()}


# ----------------------------------------------------------------- models


_SEASON_MODEL_RE = "^(au_summer|calendar|uk_summer|custom|unknown)$"


class CompetitionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    short_name: str | None = Field(default=None, max_length=100)
    association_id: UUID | None = None
    notes: str | None = None
    season_model: str = Field(default="unknown", pattern=_SEASON_MODEL_RE)
    source_system: str | None = None
    source_ref: str | None = None


class CompetitionUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    short_name: str | None = Field(default=None, max_length=100)
    status: str | None = None
    association_id: UUID | None = None
    clear_association: bool = False
    notes: str | None = None
    name_change_note: str | None = None
    season_model: str | None = Field(default=None, pattern=_SEASON_MODEL_RE)


class DivisionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source_system: str | None = None
    source_ref: str | None = None


class GradeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    program: str | None = Field(default=None, max_length=100)
    division_id: UUID | None = None
    notes: str | None = None
    source_system: str | None = None
    source_ref: str | None = None


class GradeRename(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    name_change_note: str | None = None


class SeasonCreate(BaseModel):
    label: str = Field(min_length=1, max_length=50)
    start_date: date | None = None
    end_date: date | None = None
    source_system: str | None = None
    source_ref: str | None = None


class TeamEntry(BaseModel):
    team_id: UUID
    grade_id: UUID
    season_id: UUID
    notes: str | None = None
    source_system: str | None = None
    source_ref: str | None = None


class UnresolvedClassification(BaseModel):
    source_value: str = Field(min_length=1, max_length=200)
    source_system: str | None = None
    source_ref: str | None = None
    notes: str | None = None


# ----------------------------------------------------------------- competitions


@router.post("", status_code=status.HTTP_201_CREATED)
def create_competition(workspace_id: UUID, body: CompetitionCreate, settings: SettingsDep, ctx: CompCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            cid = competitions.create_competition(
                conn, workspace_id, str(ctx.user["id"]),
                name=body.name, short_name=body.short_name, association_id=body.association_id,
                notes=body.notes, season_model=body.season_model,
                source_system=body.source_system, source_ref=body.source_ref,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return competitions.get_competition(conn, cid)


@router.get("")
def list_competitions(
    workspace_id: UUID, settings: SettingsDep, ctx: CompReadCtx,
    association_id: UUID | None = None, search: str | None = None,
) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return competitions.list_competitions(conn, association_id=association_id, search=search)


@router.get("/classifications")
def list_classifications(workspace_id: UUID, settings: SettingsDep, ctx: CompCtx, status_: str | None = None) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return competitions.list_classifications(conn, status=status_)


@router.post("/classifications/defaults", status_code=status.HTTP_201_CREATED)
def seed_default_classifications(workspace_id: UUID, settings: SettingsDep, ctx: CompCtx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return competitions.ensure_default_classifications(conn, workspace_id, str(ctx.user["id"]))


@router.post("/classifications/unresolved", status_code=status.HTTP_201_CREATED)
def record_unresolved_classification(workspace_id: UUID, body: UnresolvedClassification, settings: SettingsDep, ctx: CompCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            cid = competitions.record_unresolved_classification(
                conn, workspace_id, str(ctx.user["id"]),
                source_value=body.source_value, source_system=body.source_system,
                source_ref=body.source_ref, notes=body.notes,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return {"classification_id": str(cid), "status": "unresolved"}


@router.post("/entries", status_code=status.HTTP_201_CREATED)
def enter_team(workspace_id: UUID, body: TeamEntry, settings: SettingsDep, ctx: CompCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            result = competitions.enter_team(
                conn, workspace_id, str(ctx.user["id"]),
                team_id=body.team_id, grade_id=body.grade_id, season_id=body.season_id,
                notes=body.notes, source_system=body.source_system, source_ref=body.source_ref,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return _str_uuids(result)


@router.get("/entries")
def list_entries(
    workspace_id: UUID, settings: SettingsDep, ctx: CompCtx,
    team_id: UUID | None = None, grade_id: UUID | None = None, season_id: UUID | None = None,
) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return competitions.list_entries(conn, team_id=team_id, grade_id=grade_id, season_id=season_id)


@router.get("/{competition_id}")
def get_competition(workspace_id: UUID, competition_id: UUID, settings: SettingsDep, ctx: CompCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        comp = competitions.get_competition(conn, competition_id)
        if comp is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "competition_not_found")
        comp["name_history"] = competitions.list_name_history(conn, competition_id)
        comp["divisions"] = competitions.list_divisions(conn, competition_id)
        comp["grades"] = competitions.list_grades(conn, competition_id)
        comp["seasons"] = competitions.list_seasons(conn, competition_id)
        return comp


@router.patch("/{competition_id}")
def update_competition(workspace_id: UUID, competition_id: UUID, body: CompetitionUpdate, settings: SettingsDep, ctx: CompCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            updated = competitions.update_competition(
                conn, workspace_id, str(ctx.user["id"]), competition_id,
                name=body.name, short_name=body.short_name, status=body.status,
                association_id=body.association_id, clear_association=body.clear_association,
                notes=body.notes, name_change_note=body.name_change_note, season_model=body.season_model,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        # when the season rule changes, back-fill existing matches' seasons (manual choices preserved)
        if body.season_model is not None:
            updated["seasons_reassigned"] = seasons.reassign_competition_matches(
                conn, workspace_id, str(ctx.user["id"]), competition_id)
        return updated


@router.delete("/{competition_id}", status_code=status.HTTP_200_OK)
def delete_competition(workspace_id: UUID, competition_id: UUID, settings: SettingsDep, ctx: CompCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            competitions.delete_competition(conn, workspace_id, str(ctx.user["id"]), competition_id)
        except ValueError as exc:
            msg = str(exc)
            if msg.startswith("competition_has_matches:"):
                n = msg.split(":", 1)[1]
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    f"This competition has {n} match(es). Reassign or remove those matches before deleting it.",
                ) from exc
            raise _value_error(exc) from exc
    return {"deleted": True}


@router.get("/{competition_id}/duplicate-candidates")
def duplicate_candidates(workspace_id: UUID, competition_id: UUID, settings: SettingsDep, ctx: CompCtx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            cands = competitions.find_duplicate_candidates(conn, competition_id)
        except ValueError as exc:
            raise _value_error(exc) from exc
        return [{**c, "competition_id": str(c["competition_id"])} for c in cands]


# ----------------------------------------------------------------- divisions / grades / seasons


@router.post("/{competition_id}/divisions", status_code=status.HTTP_201_CREATED)
def create_division(workspace_id: UUID, competition_id: UUID, body: DivisionCreate, settings: SettingsDep, ctx: CompCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            did = competitions.create_division(
                conn, workspace_id, str(ctx.user["id"]), competition_id,
                name=body.name, source_system=body.source_system, source_ref=body.source_ref,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return {"division_id": str(did)}


@router.post("/{competition_id}/grades", status_code=status.HTTP_201_CREATED)
def create_grade(workspace_id: UUID, competition_id: UUID, body: GradeCreate, settings: SettingsDep, ctx: CompCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            gid = competitions.create_grade(
                conn, workspace_id, str(ctx.user["id"]), competition_id,
                name=body.name, program=body.program, division_id=body.division_id,
                notes=body.notes, source_system=body.source_system, source_ref=body.source_ref,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return {"grade_id": str(gid)}


@router.patch("/grades/{grade_id}")
def rename_grade(workspace_id: UUID, grade_id: UUID, body: GradeRename, settings: SettingsDep, ctx: CompCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _str_uuids(competitions.rename_grade(
                conn, workspace_id, str(ctx.user["id"]), grade_id,
                name=body.name, name_change_note=body.name_change_note,
            ))
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.post("/{competition_id}/seasons", status_code=status.HTTP_201_CREATED)
def create_season(workspace_id: UUID, competition_id: UUID, body: SeasonCreate, settings: SettingsDep, ctx: CompCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            sid = competitions.create_season(
                conn, workspace_id, str(ctx.user["id"]), competition_id,
                label=body.label, start_date=body.start_date, end_date=body.end_date,
                source_system=body.source_system, source_ref=body.source_ref,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return {"season_id": str(sid)}
