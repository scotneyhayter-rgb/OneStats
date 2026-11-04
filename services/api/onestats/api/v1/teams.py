"""Team endpoints (Phase 4, Stage 2).

Workspace-scoped and gated by the ``organisation.manage`` permission (teams belong to an
organisation, per D34); every mutation is audited by the domain layer. Merges are explicit and
reversible, a pair asserted "definitely different" can never be merged, and a team is never
silently reassigned to a later organisation.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from onestats.api.deps import (
    RequestContext,
    SettingsDep,
    require_any_permission,
    require_permission,
)
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import teams

router = APIRouter(prefix="/workspaces/{workspace_id}/teams", tags=["teams"])

TeamCtx = Annotated[RequestContext, Depends(require_permission("organisation.manage"))]
# Reading the team list is needed by the scorecard-entry/approval screens; holders of
# match.manage / scorecard.approve may read it even without organisation.manage. Writes stay gated above.
TeamReadCtx = Annotated[RequestContext, Depends(
    require_any_permission("organisation.manage", "match.manage", "scorecard.approve"))]

_VALUE_ERR_STATUS = {
    "team_not_found": status.HTTP_404_NOT_FOUND,
    "organisation_not_found": status.HTTP_404_NOT_FOUND,
    "merge_not_found": status.HTTP_404_NOT_FOUND,
    "asserted_distinct": status.HTTP_409_CONFLICT,
    "already_merged": status.HTTP_409_CONFLICT,
    "canonical_already_merged": status.HTTP_409_CONFLICT,
    "already_undone": status.HTTP_409_CONFLICT,
    "cannot_merge_same": status.HTTP_409_CONFLICT,
    "same_team": status.HTTP_409_CONFLICT,
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


class TeamCreate(BaseModel):
    organisation_id: UUID
    name: str = Field(min_length=1, max_length=200)
    program: str = Field(default="seniors")
    short_name: str | None = Field(default=None, max_length=100)
    is_historical: bool = False
    notes: str | None = None
    source_system: str | None = None
    source_ref: str | None = None


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    short_name: str | None = Field(default=None, max_length=100)
    program: str | None = None
    status: str | None = None
    is_historical: bool | None = None
    notes: str | None = None
    name_change_note: str | None = None


class NameHistoryAdd(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    valid_from: date | None = None
    valid_to: date | None = None
    note: str | None = None


class SourceIdentityAdd(BaseModel):
    source_system: str = Field(min_length=1, max_length=100)
    source_ref: str = Field(min_length=1, max_length=200)
    source_display_name: str | None = Field(default=None, max_length=200)


class DistinctAssert(BaseModel):
    team_a_id: UUID
    team_b_id: UUID
    reason: str | None = None


class MergeRequest(BaseModel):
    canonical_team_id: UUID
    merged_team_id: UUID
    reason: str | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
def create_team(workspace_id: UUID, body: TeamCreate, settings: SettingsDep, ctx: TeamCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            tid = teams.create_team(
                conn, workspace_id, str(ctx.user["id"]),
                organisation_id=body.organisation_id, name=body.name, program=body.program,
                short_name=body.short_name, is_historical=body.is_historical, notes=body.notes,
                source_system=body.source_system, source_ref=body.source_ref,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return teams.get_team(conn, tid)


@router.get("")
def list_teams(
    workspace_id: UUID, settings: SettingsDep, ctx: TeamReadCtx,
    organisation_id: UUID | None = None, program: str | None = None,
    include_merged: bool = False, search: str | None = None,
) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return teams.list_teams(
            conn, organisation_id=organisation_id, program=program,
            include_merged=include_merged, search=search,
        )


@router.post("/assert-distinct", status_code=status.HTTP_201_CREATED)
def assert_distinct(workspace_id: UUID, body: DistinctAssert, settings: SettingsDep, ctx: TeamCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            aid = teams.assert_distinct(
                conn, workspace_id, str(ctx.user["id"]), body.team_a_id, body.team_b_id, reason=body.reason
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return {"assertion_id": str(aid), "asserted_distinct": True}


@router.post("/merge", status_code=status.HTTP_201_CREATED)
def merge(workspace_id: UUID, body: MergeRequest, settings: SettingsDep, ctx: TeamCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            result = teams.merge_teams(
                conn, workspace_id, str(ctx.user["id"]), body.canonical_team_id, body.merged_team_id,
                reason=body.reason,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return _str_uuids(result)


@router.post("/merges/{merge_id}/undo")
def undo_merge(workspace_id: UUID, merge_id: UUID, settings: SettingsDep, ctx: TeamCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _str_uuids(teams.undo_merge(conn, workspace_id, str(ctx.user["id"]), merge_id))
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.get("/{team_id}")
def get_team(workspace_id: UUID, team_id: UUID, settings: SettingsDep, ctx: TeamCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        team = teams.get_team(conn, team_id)
        if team is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "team_not_found")
        team["name_history"] = teams.list_name_history(conn, team_id)
        team["source_identities"] = teams.list_source_identities(conn, team_id)
        return team


@router.patch("/{team_id}")
def update_team(workspace_id: UUID, team_id: UUID, body: TeamUpdate, settings: SettingsDep, ctx: TeamCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return teams.update_team(
                conn, workspace_id, str(ctx.user["id"]), team_id,
                name=body.name, short_name=body.short_name, program=body.program, status=body.status,
                is_historical=body.is_historical, notes=body.notes, name_change_note=body.name_change_note,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.post("/{team_id}/names", status_code=status.HTTP_201_CREATED)
def add_name_history(workspace_id: UUID, team_id: UUID, body: NameHistoryAdd, settings: SettingsDep, ctx: TeamCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            hid = teams.add_name_history(
                conn, workspace_id, str(ctx.user["id"]), team_id,
                name=body.name, valid_from=body.valid_from, valid_to=body.valid_to, note=body.note,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return {"name_history_id": str(hid)}


@router.post("/{team_id}/sources", status_code=status.HTTP_201_CREATED)
def add_source_identity(workspace_id: UUID, team_id: UUID, body: SourceIdentityAdd, settings: SettingsDep, ctx: TeamCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        if teams.get_team(conn, team_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "team_not_found")
        try:
            result = teams.add_source_identity(
                conn, workspace_id, str(ctx.user["id"]), team_id,
                source_system=body.source_system, source_ref=body.source_ref,
                source_display_name=body.source_display_name,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return _str_uuids(result)


@router.get("/{team_id}/duplicate-candidates")
def duplicate_candidates(workspace_id: UUID, team_id: UUID, settings: SettingsDep, ctx: TeamCtx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            cands = teams.find_duplicate_candidates(conn, team_id)
        except ValueError as exc:
            raise _value_error(exc) from exc
        return [{**c, "team_id": str(c["team_id"])} for c in cands]
