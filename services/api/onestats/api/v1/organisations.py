"""Organisation & historical-identity endpoints (Phase 4, Stage 1).

All routes are workspace-scoped and gated by the ``organisation.manage`` permission; every
mutation is audited by the domain layer. Merges are explicit and reversible, and a pair
asserted "definitely different" can never be merged.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import organisations

router = APIRouter(prefix="/workspaces/{workspace_id}/organisations", tags=["organisations"])

OrgCtx = Annotated[RequestContext, Depends(require_permission("organisation.manage"))]

_VALUE_ERR_STATUS = {
    "organisation_not_found": status.HTTP_404_NOT_FOUND,
    "merge_not_found": status.HTTP_404_NOT_FOUND,
    "asserted_distinct": status.HTTP_409_CONFLICT,
    "already_merged": status.HTTP_409_CONFLICT,
    "canonical_already_merged": status.HTTP_409_CONFLICT,
    "already_undone": status.HTTP_409_CONFLICT,
    "cannot_merge_same": status.HTTP_409_CONFLICT,
    "same_organisation": status.HTTP_409_CONFLICT,
}


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


def _value_error(exc: ValueError) -> HTTPException:
    code = str(exc)
    return HTTPException(_VALUE_ERR_STATUS.get(code, status.HTTP_400_BAD_REQUEST), code)


# --------------------------------------------------------------------------- models


class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(default="club")
    short_name: str | None = Field(default=None, max_length=60)
    is_historical: bool = False
    notes: str | None = None
    source_system: str | None = None
    source_ref: str | None = None


class OrgUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    short_name: str | None = Field(default=None, max_length=60)
    kind: str | None = None
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
    organisation_a_id: UUID
    organisation_b_id: UUID
    reason: str | None = None


class MergeRequest(BaseModel):
    canonical_organisation_id: UUID
    merged_organisation_id: UUID
    reason: str | None = None


# --------------------------------------------------------------------------- routes


@router.post("", status_code=status.HTTP_201_CREATED)
def create_organisation(
    workspace_id: UUID, body: OrgCreate, settings: SettingsDep, ctx: OrgCtx
) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            org_id = organisations.create_organisation(
                conn, workspace_id, str(ctx.user["id"]),
                name=body.name, kind=body.kind, short_name=body.short_name,
                is_historical=body.is_historical, notes=body.notes,
                source_system=body.source_system, source_ref=body.source_ref,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return organisations.get_organisation(conn, org_id)


@router.get("")
def list_organisations(
    workspace_id: UUID, settings: SettingsDep, ctx: OrgCtx,
    include_merged: bool = False, kind: str | None = None,
) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return organisations.list_organisations(conn, include_merged=include_merged, kind=kind)


@router.post("/assert-distinct", status_code=status.HTTP_201_CREATED)
def assert_distinct(
    workspace_id: UUID, body: DistinctAssert, settings: SettingsDep, ctx: OrgCtx
) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            assertion_id = organisations.assert_distinct(
                conn, workspace_id, str(ctx.user["id"]),
                body.organisation_a_id, body.organisation_b_id, reason=body.reason,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return {"assertion_id": str(assertion_id), "asserted_distinct": True}


@router.post("/merge", status_code=status.HTTP_201_CREATED)
def merge(workspace_id: UUID, body: MergeRequest, settings: SettingsDep, ctx: OrgCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            result = organisations.merge_organisations(
                conn, workspace_id, str(ctx.user["id"]),
                body.canonical_organisation_id, body.merged_organisation_id, reason=body.reason,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return {k: str(v) for k, v in result.items()}


@router.post("/merges/{merge_id}/undo")
def undo_merge(
    workspace_id: UUID, merge_id: UUID, settings: SettingsDep, ctx: OrgCtx
) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            result = organisations.undo_merge(conn, workspace_id, str(ctx.user["id"]), merge_id)
        except ValueError as exc:
            raise _value_error(exc) from exc
        return {k: (str(v) if isinstance(v, UUID) else v) for k, v in result.items()}


@router.get("/{organisation_id}")
def get_organisation(
    workspace_id: UUID, organisation_id: UUID, settings: SettingsDep, ctx: OrgCtx
) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        org = organisations.get_organisation(conn, organisation_id)
        if org is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "organisation_not_found")
        org["name_history"] = organisations.list_name_history(conn, organisation_id)
        org["source_identities"] = organisations.list_source_identities(conn, organisation_id)
        return org


@router.patch("/{organisation_id}")
def update_organisation(
    workspace_id: UUID, organisation_id: UUID, body: OrgUpdate, settings: SettingsDep, ctx: OrgCtx
) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return organisations.update_organisation(
                conn, workspace_id, str(ctx.user["id"]), organisation_id,
                name=body.name, short_name=body.short_name, kind=body.kind, status=body.status,
                is_historical=body.is_historical, notes=body.notes,
                name_change_note=body.name_change_note,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.post("/{organisation_id}/names", status_code=status.HTTP_201_CREATED)
def add_name_history(
    workspace_id: UUID, organisation_id: UUID, body: NameHistoryAdd, settings: SettingsDep, ctx: OrgCtx
) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            hist_id = organisations.add_name_history(
                conn, workspace_id, str(ctx.user["id"]), organisation_id,
                name=body.name, valid_from=body.valid_from, valid_to=body.valid_to, note=body.note,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return {"name_history_id": str(hist_id)}


@router.post("/{organisation_id}/sources", status_code=status.HTTP_201_CREATED)
def add_source_identity(
    workspace_id: UUID, organisation_id: UUID, body: SourceIdentityAdd, settings: SettingsDep, ctx: OrgCtx
) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        if organisations.get_organisation(conn, organisation_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "organisation_not_found")
        try:
            result = organisations.add_source_identity(
                conn, workspace_id, str(ctx.user["id"]), organisation_id,
                source_system=body.source_system, source_ref=body.source_ref,
                source_display_name=body.source_display_name,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return {k: (str(v) if isinstance(v, UUID) else v) for k, v in result.items()}


@router.get("/{organisation_id}/duplicate-candidates")
def duplicate_candidates(
    workspace_id: UUID, organisation_id: UUID, settings: SettingsDep, ctx: OrgCtx
) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            cands = organisations.find_duplicate_candidates(conn, organisation_id)
        except ValueError as exc:
            raise _value_error(exc) from exc
        return [{**c, "organisation_id": str(c["organisation_id"])} for c in cands]
