"""Organisation-relationship & timeline endpoints (Phase 4, Stage 5).

Workspace-scoped and gated by ``organisation.manage``; mutations are audited. Relationships link
distinct organisations (mergers/amalgamations, renames, affiliations, association transfers,
predecessor/successor) and never trigger a Stage 1 identity merge. Cycles and overlapping
exclusive affiliations are rejected; relationships are reversible (void/restore) and correctable.
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
from onestats.domain import relationships

router = APIRouter(prefix="/workspaces/{workspace_id}/organisation-relationships", tags=["organisation-relationships"])

RelCtx = Annotated[RequestContext, Depends(require_permission("organisation.manage"))]

_VALUE_ERR_STATUS = {
    "organisation_not_found": status.HTTP_404_NOT_FOUND,
    "relationship_not_found": status.HTTP_404_NOT_FOUND,
    "relationship_cycle": status.HTTP_409_CONFLICT,
    "overlapping_affiliation": status.HTTP_409_CONFLICT,
    "self_relationship": status.HTTP_409_CONFLICT,
    "already_void": status.HTTP_409_CONFLICT,
    "not_void": status.HTTP_409_CONFLICT,
}


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


def _value_error(exc: ValueError) -> HTTPException:
    code = str(exc)
    return HTTPException(_VALUE_ERR_STATUS.get(code, status.HTTP_400_BAD_REQUEST), code)


class RelationshipCreate(BaseModel):
    from_org_id: UUID
    to_org_id: UUID
    rel_type: str = Field(pattern="^(merger|amalgamation|rename|affiliation|association_transfer|predecessor|successor|other)$")
    valid_from: date | None = None
    valid_to: date | None = None
    notes: str | None = None
    evidence: str | None = None
    source_system: str | None = None
    source_ref: str | None = None


class RelationshipCorrect(BaseModel):
    valid_from: date | None = None
    valid_to: date | None = None
    set_dates: bool = False
    notes: str | None = None
    evidence: str | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
def create_relationship(workspace_id: UUID, body: RelationshipCreate, settings: SettingsDep, ctx: RelCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            rel_id = relationships.create_relationship(
                conn, workspace_id, str(ctx.user["id"]),
                from_org_id=body.from_org_id, to_org_id=body.to_org_id, rel_type=body.rel_type,
                valid_from=body.valid_from, valid_to=body.valid_to, notes=body.notes,
                evidence=body.evidence, source_system=body.source_system, source_ref=body.source_ref,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc
        return relationships.get_relationship(conn, rel_id)


@router.get("")
def list_for_org(
    workspace_id: UUID, organisation_id: UUID, settings: SettingsDep, ctx: RelCtx,
    include_void: bool = False, direction: str = "both",
) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return relationships.list_relationships(
            conn, organisation_id, include_void=include_void, direction=direction
        )


@router.get("/timeline")
def timeline(workspace_id: UUID, organisation_id: UUID, settings: SettingsDep, ctx: RelCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return relationships.organisation_timeline(conn, organisation_id)
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.get("/affiliation")
def resolve_affiliation(
    workspace_id: UUID, organisation_id: UUID, on_date: date, settings: SettingsDep, ctx: RelCtx
) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        result = relationships.resolve_affiliation(conn, organisation_id, on_date)
        if result is None:
            return {"affiliation": None, "known": False}  # undocumented — not guessed
        return {"affiliation": {k: (str(v) if isinstance(v, UUID) else v) for k, v in result.items()},
                "known": True}


@router.patch("/{relationship_id}")
def correct_relationship(workspace_id: UUID, relationship_id: UUID, body: RelationshipCorrect, settings: SettingsDep, ctx: RelCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return relationships.correct_relationship(
                conn, workspace_id, str(ctx.user["id"]), relationship_id,
                valid_from=body.valid_from, valid_to=body.valid_to, set_dates=body.set_dates,
                notes=body.notes, evidence=body.evidence,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.post("/{relationship_id}/void")
def void_relationship(workspace_id: UUID, relationship_id: UUID, settings: SettingsDep, ctx: RelCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return relationships.void_relationship(conn, workspace_id, str(ctx.user["id"]), relationship_id)
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.post("/{relationship_id}/restore")
def restore_relationship(workspace_id: UUID, relationship_id: UUID, settings: SettingsDep, ctx: RelCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return relationships.restore_relationship(conn, workspace_id, str(ctx.user["id"]), relationship_id)
        except ValueError as exc:
            raise _value_error(exc) from exc
