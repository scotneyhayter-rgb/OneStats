"""CricketStatz player/official import endpoints (Phase 5, Stage 5).

Workspace-scoped, gated by ``import.manage``, audited. Staging-first: stage → detect →
administrator review → promote, with reconcile and rollback. Promotes into the Phase 5 person
model (never overwriting verified identities); a name match never auto-merges.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import imports, people_import

router = APIRouter(prefix="/workspaces/{workspace_id}/people-imports", tags=["people-import"])

PICtx = Annotated[RequestContext, Depends(require_permission("import.manage"))]

_VALUE_ERR_STATUS = {
    "batch_not_found": status.HTTP_404_NOT_FOUND,
    "record_not_found": status.HTTP_404_NOT_FOUND,
    "no_people_collections": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "invalid_payload": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "existing_person_required": status.HTTP_400_BAD_REQUEST,
    "invalid_decision": status.HTTP_400_BAD_REQUEST,
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


class StageRequest(BaseModel):
    data: dict[str, Any] = Field(description="CricketStatz export (players[] and/or officials[])")
    filename: str | None = None
    source_system: str | None = None


class RecordDecision(BaseModel):
    decision: str = Field(pattern="^(new|existing|distinct|defer|reject)$")
    existing_person_id: UUID | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
def stage(workspace_id: UUID, body: StageRequest, settings: SettingsDep, ctx: PICtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _ids(people_import.stage_people(
                conn, workspace_id, str(ctx.user["id"]), payload=body.data, filename=body.filename,
                source_system=body.source_system or people_import.SOURCE_SYSTEM))
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.get("")
def list_batches(workspace_id: UUID, settings: SettingsDep, ctx: PICtx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_ids(b) for b in imports.list_batches(conn)]


@router.post("/{batch_id}/detect")
def detect(workspace_id: UUID, batch_id: UUID, settings: SettingsDep, ctx: PICtx, source_system: str | None = None) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return people_import.detect(conn, workspace_id, str(ctx.user["id"]), batch_id,
                                        source_system=source_system or people_import.SOURCE_SYSTEM)
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.get("/{batch_id}/records")
def list_records(
    workspace_id: UUID, batch_id: UUID, settings: SettingsDep, ctx: PICtx,
    entity_type: str | None = None, status_: str | None = None,
) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_ids(r) for r in imports.list_records(conn, batch_id, entity_type=entity_type, status=status_)]


@router.post("/{batch_id}/records/{record_id}/decide")
def decide_record(workspace_id: UUID, batch_id: UUID, record_id: UUID, body: RecordDecision, settings: SettingsDep, ctx: PICtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return people_import.decide_record(
                conn, workspace_id, str(ctx.user["id"]), record_id, decision=body.decision,
                existing_person_id=body.existing_person_id)
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.post("/{batch_id}/promote")
def promote(workspace_id: UUID, batch_id: UUID, settings: SettingsDep, ctx: PICtx, source_system: str | None = None) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return people_import.promote(conn, workspace_id, str(ctx.user["id"]), batch_id,
                                         source_system=source_system or people_import.SOURCE_SYSTEM)
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.post("/{batch_id}/rollback")
def rollback(workspace_id: UUID, batch_id: UUID, settings: SettingsDep, ctx: PICtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return people_import.rollback(conn, workspace_id, str(ctx.user["id"]), batch_id)
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.get("/{batch_id}/reconcile")
def reconcile(workspace_id: UUID, batch_id: UUID, settings: SettingsDep, ctx: PICtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return people_import.reconcile(conn, batch_id)
        except ValueError as exc:
            raise _value_error(exc) from exc
