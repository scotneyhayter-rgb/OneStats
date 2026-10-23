"""People & player-identity endpoints (Phase 5, Stage 1).

Workspace-scoped, gated by ``person.manage``, audited. Junior personal data is hidden by default;
a manager may request it with ``include_protected=true``. No identity merges here (Stage 3) —
``/duplicate-candidates`` only suggests, never merges, and a shared name/initials is never proof.
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
from onestats.domain import people

router = APIRouter(prefix="/workspaces/{workspace_id}/people", tags=["people"])

PersonCtx = Annotated[RequestContext, Depends(require_permission("person.manage"))]

_VALUE_ERR_STATUS = {
    "person_not_found": status.HTTP_404_NOT_FOUND,
    "invalid_role": status.HTTP_400_BAD_REQUEST,
    "invalid_name_type": status.HTTP_400_BAD_REQUEST,
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


class PersonCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    dob: date | None = None
    dob_precision: str = "unknown"
    is_junior: bool = False
    privacy_protected: bool | None = None
    notes: str | None = None
    roles: list[str] = Field(default_factory=list)
    source_system: str | None = None
    source_ref: str | None = None


class PersonUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    status: str | None = None
    is_junior: bool | None = None
    privacy_protected: bool | None = None
    dob: date | None = None
    dob_precision: str | None = None
    set_dob: bool = False
    notes: str | None = None
    name_change_note: str | None = None


class NameAdd(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    name_type: str = Field(default="alias", pattern="^(primary|alias|initials|maiden|incomplete|other)$")
    valid_from: date | None = None
    valid_to: date | None = None
    note: str | None = None


class SourceIdentityAdd(BaseModel):
    source_system: str = Field(min_length=1, max_length=100)
    source_ref: str = Field(min_length=1, max_length=200)
    source_display_name: str | None = Field(default=None, max_length=200)


class RoleAdd(BaseModel):
    role: str = Field(pattern="^(player|umpire|scorer|coach|administrator|selector|captain|other)$")


@router.post("", status_code=status.HTTP_201_CREATED)
def create_person(workspace_id: UUID, body: PersonCreate, settings: SettingsDep, ctx: PersonCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            pid = people.create_person(
                conn, workspace_id, str(ctx.user["id"]), display_name=body.display_name,
                dob=body.dob, dob_precision=body.dob_precision, is_junior=body.is_junior,
                privacy_protected=body.privacy_protected, notes=body.notes, roles=body.roles,
                source_system=body.source_system, source_ref=body.source_ref,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return _ids(people.detail(conn, pid, include_protected=True))


@router.get("")
def list_people(
    workspace_id: UUID, settings: SettingsDep, ctx: PersonCtx,
    search: str | None = None, role: str | None = None,
    include_merged: bool = False, include_protected: bool = False,
) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_ids(p) for p in people.list_people(
            conn, search=search, role=role, include_merged=include_merged, include_protected=include_protected)]


@router.get("/{person_id}")
def get_person(workspace_id: UUID, person_id: UUID, settings: SettingsDep, ctx: PersonCtx, include_protected: bool = False) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        d = people.detail(conn, person_id, include_protected=include_protected)
        if d is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "person_not_found")
        d["names"] = [_ids(n) for n in d["names"]]
        d["source_identities"] = [_ids(s) for s in d["source_identities"]]
        return _ids(d)


@router.patch("/{person_id}")
def update_person(workspace_id: UUID, person_id: UUID, body: PersonUpdate, settings: SettingsDep, ctx: PersonCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _ids(people.update_person(
                conn, workspace_id, str(ctx.user["id"]), person_id,
                display_name=body.display_name, status=body.status, is_junior=body.is_junior,
                privacy_protected=body.privacy_protected, dob=body.dob, dob_precision=body.dob_precision,
                set_dob=body.set_dob, notes=body.notes, name_change_note=body.name_change_note,
            ))
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.post("/{person_id}/names", status_code=status.HTTP_201_CREATED)
def add_name(workspace_id: UUID, person_id: UUID, body: NameAdd, settings: SettingsDep, ctx: PersonCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            nid = people.add_name(
                conn, workspace_id, str(ctx.user["id"]), person_id, name=body.name,
                name_type=body.name_type, valid_from=body.valid_from, valid_to=body.valid_to, note=body.note,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return {"name_id": str(nid)}


@router.post("/{person_id}/sources", status_code=status.HTTP_201_CREATED)
def add_source(workspace_id: UUID, person_id: UUID, body: SourceIdentityAdd, settings: SettingsDep, ctx: PersonCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        if people.get_person(conn, person_id, include_protected=True) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "person_not_found")
        try:
            result = people.add_source_identity(
                conn, workspace_id, str(ctx.user["id"]), person_id,
                source_system=body.source_system, source_ref=body.source_ref,
                source_display_name=body.source_display_name,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return _ids(result)


@router.post("/{person_id}/roles", status_code=status.HTTP_201_CREATED)
def add_role(workspace_id: UUID, person_id: UUID, body: RoleAdd, settings: SettingsDep, ctx: PersonCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _ids(people.add_role(conn, workspace_id, str(ctx.user["id"]), person_id, body.role))
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.delete("/{person_id}/roles/{role}")
def remove_role(workspace_id: UUID, person_id: UUID, role: str, settings: SettingsDep, ctx: PersonCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return {"removed": people.remove_role(conn, workspace_id, str(ctx.user["id"]), person_id, role)}


@router.get("/{person_id}/duplicate-candidates")
def duplicate_candidates(workspace_id: UUID, person_id: UUID, settings: SettingsDep, ctx: PersonCtx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            cands = people.find_duplicate_candidates(conn, person_id)
        except ValueError as exc:
            raise _value_error(exc) from exc
        return [{**c, "person_id": str(c["person_id"])} for c in cands]
