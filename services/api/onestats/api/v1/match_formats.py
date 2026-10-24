"""Workspace-configurable match-format endpoints (Phase 7, Stage 7.5).

Listing is available to match editors (for the dropdown); enabling/disabling, setting the default
and creating custom formats require ``workspace.manage``. Workspace-scoped and audited.
"""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import match_formats

router = APIRouter(prefix="/workspaces/{workspace_id}/match-formats", tags=["match-formats"])

ViewCtx = Annotated[RequestContext, Depends(require_permission("match.manage"))]
AdminCtx = Annotated[RequestContext, Depends(require_permission("workspace.manage"))]

_ERR = {
    "format_not_found": status.HTTP_404_NOT_FOUND,
    "cannot_default_disabled_format": status.HTTP_409_CONFLICT,
    "missing_label": status.HTTP_422_UNPROCESSABLE_ENTITY,
}


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


def _value_error(exc: ValueError) -> HTTPException:
    return HTTPException(_ERR.get(str(exc), status.HTTP_400_BAD_REQUEST), str(exc))


def _ids(d: dict[str, Any]) -> dict[str, Any]:
    return {k: (str(v) if isinstance(v, UUID) else v) for k, v in d.items()}


class CustomFormat(BaseModel):
    label: str = Field(min_length=1, max_length=100)


class FormatPatch(BaseModel):
    enabled: bool | None = None
    is_default: bool | None = None


@router.get("")
def list_formats(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx, enabled_only: bool = False) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_ids(f) for f in match_formats.list_formats(conn, workspace_id, enabled_only=enabled_only)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_custom(workspace_id: UUID, body: CustomFormat, settings: SettingsDep, ctx: AdminCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _ids(match_formats.create_custom(conn, workspace_id, str(ctx.user["id"]), body.label))
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.patch("/{format_id}")
def update_format(workspace_id: UUID, format_id: UUID, body: FormatPatch, settings: SettingsDep, ctx: AdminCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            out = None
            if body.enabled is not None:
                out = match_formats.set_enabled(conn, workspace_id, str(ctx.user["id"]), format_id, body.enabled)
            if body.is_default:
                out = match_formats.set_default(conn, workspace_id, str(ctx.user["id"]), format_id)
            if out is None:
                raise ValueError("format_not_found")
            return _ids(out)
        except ValueError as exc:
            raise _value_error(exc) from exc
