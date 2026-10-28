"""Cricket Statz structural-import endpoints (Phase 4, Stage 6).

Workspace-scoped, gated by ``import.manage``, audited. Staging-first: upload stages rows,
validate/preview inspect them, and promote (explicit admin approval) writes only confirmed
structural entities into canonical tables. Cancel/rollback reverse a batch. No scorecards.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import imports
from onestats.domain.importing import adapters as _adapters  # noqa: F401 - import registers adapters
from onestats.domain.importing import detect_adapter, get_adapter, pipeline, registry

router = APIRouter(prefix="/workspaces/{workspace_id}/imports", tags=["imports"])

ImportCtx = Annotated[RequestContext, Depends(require_permission("import.manage"))]

_VALUE_ERR_STATUS = {
    "batch_not_found": status.HTTP_404_NOT_FOUND,
    "no_importable_collections": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "invalid_payload": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "batch_has_promoted_rows_use_rollback": status.HTTP_409_CONFLICT,
    "batch_cancelled": status.HTTP_409_CONFLICT,
    "batch_promoted": status.HTTP_409_CONFLICT,
    "unrecognised_format": status.HTTP_422_UNPROCESSABLE_ENTITY,
}


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


def _value_error(exc: ValueError) -> HTTPException:
    code = str(exc)
    return HTTPException(_VALUE_ERR_STATUS.get(code, status.HTTP_400_BAD_REQUEST), code)


def _ids_to_str(d: dict[str, Any]) -> dict[str, Any]:
    return {k: (str(v) if isinstance(v, UUID) else v) for k, v in d.items()}


class StageRequest(BaseModel):
    data: dict[str, Any] = Field(description="Cricket Statz export payload (clubs/teams/venues/divisions/matches)")
    filename: str | None = None
    source_system: str | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
def stage(workspace_id: UUID, body: StageRequest, settings: SettingsDep, ctx: ImportCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _ids_to_str(
                imports.parse_and_stage(conn, workspace_id, str(ctx.user["id"]), payload=body.data, filename=body.filename)
            )
        except ValueError as exc:
            raise _value_error(exc) from exc


class CricketStatzRequest(BaseModel):
    data: dict[str, Any] = Field(description="Sliced CricketStatz payload: structural + scorecards")
    people: dict[str, Any] | None = Field(default=None, description="Referenced players/officials")
    commit: bool = Field(default=False, description="False = preview (nothing persists); True = import")
    filename: str | None = None
    competition_id: UUID | None = Field(default=None, description="Existing competition to import into")
    competition_name: str | None = Field(default=None, description="New competition name (found-or-created)")


@router.post("/cricketstatz")
def cricketstatz_import(
    workspace_id: UUID, body: CricketStatzRequest, settings: SettingsDep, ctx: ImportCtx
) -> dict[str, Any]:
    """Controlled CricketStatz import for the Import Wizard. A preview runs the full analysis inside
    a savepoint that is rolled back (nothing persists); a commit releases it. Workspace-isolated and
    gated by ``import.manage``; idempotent (no duplicate records)."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        sp = conn.begin_nested()
        try:
            result = imports.controlled_import(
                conn, workspace_id, str(ctx.user["id"]),
                data=body.data, people=body.people, commit=body.commit, filename=body.filename,
                competition_id=body.competition_id, competition_name=body.competition_name,
            )
        except ValueError as exc:
            sp.rollback()
            raise _value_error(exc) from exc
        if body.commit:
            sp.commit()       # release: the outer workspace_transaction commits
        else:
            sp.rollback()     # preview only — discard all staging/promotion
        return result


class GenericImportRequest(BaseModel):
    content: str | None = Field(default=None, description="Text source (CSV/JSON/XML)")
    content_base64: str | None = Field(default=None, description="Base64 of a binary source (Excel)")
    filename: str | None = None
    format_id: str | None = Field(default=None, description="Adapter id; auto-detected when omitted")
    commit: bool = Field(default=False, description="False = preview (nothing persists); True = import")


def _content(body: GenericImportRequest) -> bytes | str:
    if body.content_base64 is not None:
        import base64
        try:
            return base64.b64decode(body.content_base64)
        except Exception as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_base64") from exc
    if body.content is not None:
        return body.content
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "no_content")


@router.post("/detect")
def detect_import_format(workspace_id: UUID, body: GenericImportRequest, settings: SettingsDep, ctx: ImportCtx) -> dict[str, Any]:
    """Which registered adapters recognise this file, best first (so the wizard can confirm/choose)."""
    hits = registry.detect(_content(body), body.filename)
    return {"candidates": [{"format_id": a.format_id, "display_name": a.display_name,
                            "confidence": round(c, 3)} for a, c in hits]}


@router.post("/generic")
def generic_import(workspace_id: UUID, body: GenericImportRequest, settings: SettingsDep, ctx: ImportCtx) -> dict[str, Any]:
    """Universal import: detect/parse/normalise a file via its adapter, then stage+promote through the
    one shared pipeline. A preview runs inside a savepoint that is rolled back (nothing persists); a
    commit releases it. Workspace-isolated, gated by ``import.manage``; imported matches are draft."""
    content = _content(body)
    adapter = get_adapter(body.format_id) if body.format_id else detect_adapter(content, body.filename)
    if adapter is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unrecognised_format")
    try:
        dataset = adapter.normalize(adapter.parse(content, filename=body.filename))
    except ValueError as exc:
        raise _value_error(exc) from exc
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        sp = conn.begin_nested()
        try:
            result = pipeline.import_dataset(conn, workspace_id, str(ctx.user["id"]),
                                             dataset=dataset, commit=body.commit, filename=body.filename)
        except ValueError as exc:
            sp.rollback()
            raise _value_error(exc) from exc
        if body.commit:
            sp.commit()
        else:
            sp.rollback()
        return {"format_id": adapter.format_id, "display_name": adapter.display_name, **result}


@router.get("")
def list_batches(workspace_id: UUID, settings: SettingsDep, ctx: ImportCtx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_ids_to_str(b) for b in imports.list_batches(conn)]


@router.get("/{batch_id}")
def get_batch(workspace_id: UUID, batch_id: UUID, settings: SettingsDep, ctx: ImportCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        batch = imports.get_batch(conn, batch_id)
        if batch is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "batch_not_found")
        return {"batch": _ids_to_str(batch), "preview": imports.preview_batch(conn, batch_id)}


@router.get("/{batch_id}/records")
def list_records(
    workspace_id: UUID, batch_id: UUID, settings: SettingsDep, ctx: ImportCtx,
    entity_type: str | None = None, status_: str | None = None,
) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_ids_to_str(r) for r in imports.list_records(conn, batch_id, entity_type=entity_type, status=status_)]


@router.post("/{batch_id}/validate")
def validate(workspace_id: UUID, batch_id: UUID, settings: SettingsDep, ctx: ImportCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _ids_to_str(imports.validate_batch(conn, workspace_id, str(ctx.user["id"]), batch_id))
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.post("/{batch_id}/promote")
def promote(workspace_id: UUID, batch_id: UUID, settings: SettingsDep, ctx: ImportCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return imports.promote_batch(conn, workspace_id, str(ctx.user["id"]), batch_id)
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.post("/{batch_id}/cancel")
def cancel(workspace_id: UUID, batch_id: UUID, settings: SettingsDep, ctx: ImportCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return imports.cancel_batch(conn, workspace_id, str(ctx.user["id"]), batch_id)
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.post("/{batch_id}/rollback")
def rollback(workspace_id: UUID, batch_id: UUID, settings: SettingsDep, ctx: ImportCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return imports.rollback_batch(conn, workspace_id, str(ctx.user["id"]), batch_id)
        except ValueError as exc:
            raise _value_error(exc) from exc
