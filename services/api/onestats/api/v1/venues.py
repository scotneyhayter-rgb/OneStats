"""Venue (ground) endpoints (Phase 4, Stage 2).

Workspace-scoped and gated by the ``venue.manage`` permission (D34); every mutation is audited by
the domain layer. Merges are explicit and reversible, and a pair asserted "definitely different"
can never be merged. Missing addresses/coordinates are never invented.
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
from onestats.domain import venues

router = APIRouter(prefix="/workspaces/{workspace_id}/venues", tags=["venues"])

VenueCtx = Annotated[RequestContext, Depends(require_permission("venue.manage"))]
# Reading the venue list is needed by the scorecard-entry/approval screens; holders of
# match.manage / scorecard.approve may read it even without venue.manage. Writes stay gated above.
VenueReadCtx = Annotated[RequestContext, Depends(
    require_any_permission("venue.manage", "match.manage", "scorecard.approve"))]

_VALUE_ERR_STATUS = {
    "venue_not_found": status.HTTP_404_NOT_FOUND,
    "merge_not_found": status.HTTP_404_NOT_FOUND,
    "asserted_distinct": status.HTTP_409_CONFLICT,
    "already_merged": status.HTTP_409_CONFLICT,
    "canonical_already_merged": status.HTTP_409_CONFLICT,
    "already_undone": status.HTTP_409_CONFLICT,
    "cannot_merge_same": status.HTTP_409_CONFLICT,
    "same_venue": status.HTTP_409_CONFLICT,
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


class VenueCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    short_name: str | None = Field(default=None, max_length=100)
    address: str | None = None
    locality: str | None = None
    region: str | None = None
    country: str | None = None
    postcode: str | None = Field(default=None, max_length=20)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    notes: str | None = None
    source_system: str | None = None
    source_ref: str | None = None


class VenueUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    short_name: str | None = Field(default=None, max_length=100)
    status: str | None = None
    address: str | None = None
    locality: str | None = None
    region: str | None = None
    country: str | None = None
    postcode: str | None = Field(default=None, max_length=20)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
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
    venue_a_id: UUID
    venue_b_id: UUID
    reason: str | None = None


class MergeRequest(BaseModel):
    canonical_venue_id: UUID
    merged_venue_id: UUID
    reason: str | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
def create_venue(workspace_id: UUID, body: VenueCreate, settings: SettingsDep, ctx: VenueCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            vid = venues.create_venue(
                conn, workspace_id, str(ctx.user["id"]),
                name=body.name, short_name=body.short_name, address=body.address,
                locality=body.locality, region=body.region, country=body.country,
                postcode=body.postcode, latitude=body.latitude, longitude=body.longitude,
                notes=body.notes, source_system=body.source_system, source_ref=body.source_ref,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return venues.get_venue(conn, vid)


@router.get("")
def list_venues(
    workspace_id: UUID, settings: SettingsDep, ctx: VenueReadCtx,
    include_merged: bool = False, search: str | None = None,
) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return venues.list_venues(conn, include_merged=include_merged, search=search)


@router.post("/assert-distinct", status_code=status.HTTP_201_CREATED)
def assert_distinct(workspace_id: UUID, body: DistinctAssert, settings: SettingsDep, ctx: VenueCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            aid = venues.assert_distinct(
                conn, workspace_id, str(ctx.user["id"]), body.venue_a_id, body.venue_b_id, reason=body.reason
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return {"assertion_id": str(aid), "asserted_distinct": True}


@router.post("/merge", status_code=status.HTTP_201_CREATED)
def merge(workspace_id: UUID, body: MergeRequest, settings: SettingsDep, ctx: VenueCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            result = venues.merge_venues(
                conn, workspace_id, str(ctx.user["id"]), body.canonical_venue_id, body.merged_venue_id,
                reason=body.reason,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return _str_uuids(result)


@router.post("/merges/{merge_id}/undo")
def undo_merge(workspace_id: UUID, merge_id: UUID, settings: SettingsDep, ctx: VenueCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _str_uuids(venues.undo_merge(conn, workspace_id, str(ctx.user["id"]), merge_id))
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.get("/{venue_id}")
def get_venue(workspace_id: UUID, venue_id: UUID, settings: SettingsDep, ctx: VenueCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        venue = venues.get_venue(conn, venue_id)
        if venue is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "venue_not_found")
        venue["name_history"] = venues.list_name_history(conn, venue_id)
        venue["source_identities"] = venues.list_source_identities(conn, venue_id)
        return venue


@router.patch("/{venue_id}")
def update_venue(workspace_id: UUID, venue_id: UUID, body: VenueUpdate, settings: SettingsDep, ctx: VenueCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return venues.update_venue(
                conn, workspace_id, str(ctx.user["id"]), venue_id,
                name_change_note=body.name_change_note,
                **body.model_dump(exclude={"name_change_note"}, exclude_none=True),
            )
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.post("/{venue_id}/names", status_code=status.HTTP_201_CREATED)
def add_name_history(workspace_id: UUID, venue_id: UUID, body: NameHistoryAdd, settings: SettingsDep, ctx: VenueCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            hid = venues.add_name_history(
                conn, workspace_id, str(ctx.user["id"]), venue_id,
                name=body.name, valid_from=body.valid_from, valid_to=body.valid_to, note=body.note,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return {"name_history_id": str(hid)}


@router.post("/{venue_id}/sources", status_code=status.HTTP_201_CREATED)
def add_source_identity(workspace_id: UUID, venue_id: UUID, body: SourceIdentityAdd, settings: SettingsDep, ctx: VenueCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        if venues.get_venue(conn, venue_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "venue_not_found")
        try:
            result = venues.add_source_identity(
                conn, workspace_id, str(ctx.user["id"]), venue_id,
                source_system=body.source_system, source_ref=body.source_ref,
                source_display_name=body.source_display_name,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return _str_uuids(result)


@router.get("/{venue_id}/duplicate-candidates")
def duplicate_candidates(workspace_id: UUID, venue_id: UUID, settings: SettingsDep, ctx: VenueCtx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            cands = venues.find_duplicate_candidates(conn, venue_id)
        except ValueError as exc:
            raise _value_error(exc) from exc
        return [{**c, "venue_id": str(c["venue_id"])} for c in cands]
