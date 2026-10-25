"""Publishing management endpoints (Phase 15, deliverable 29) — admin side, workspace-scoped.

Create/list publications, publish/unpublish/revoke, refresh snapshots, and download the static-export
files for existing website hosting. Public serving is the separate unauthenticated ``/public`` router.
"""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import publishing

router = APIRouter(prefix="/workspaces/{workspace_id}/publications", tags=["publishing"])

ManageCtx = Annotated[RequestContext, Depends(require_permission("workspace.manage"))]

_ERRORS = {
    "invalid_kind": status.HTTP_400_BAD_REQUEST,
    "unknown_report": status.HTTP_400_BAD_REQUEST,
    "person_required": status.HTTP_400_BAD_REQUEST,
    "invalid_status": status.HTTP_400_BAD_REQUEST,
    "publication_not_found": status.HTTP_404_NOT_FOUND,
}


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


def _err(exc: ValueError) -> HTTPException:
    return HTTPException(_ERRORS.get(str(exc), status.HTTP_400_BAD_REQUEST), str(exc))


class PublishBody(BaseModel):
    kind: str = Field(pattern="^(report|player_profile)$")
    title: str = Field(min_length=1, max_length=200)
    report_id: str | None = None
    person_id: UUID | None = None
    filters: dict[str, Any] = Field(default_factory=dict)


class StatusBody(BaseModel):
    status: str = Field(pattern="^(published|unpublished|revoked)$")


def _public_urls(settings, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    base = settings.public_base_url
    for r in rows:
        path = ("p/" if r["kind"] == "player_profile" else "r/") + r["slug"]
        r["public_path"] = f"/api/v1/public/{path}"
        r["json_path"] = f"/api/v1/public/r/{r['slug']}.json"
        r["public_url"] = f"{base.rstrip('/')}{r['public_path']}" if base else None
    return rows


@router.get("")
def list_publications(workspace_id: UUID, settings: SettingsDep, ctx: ManageCtx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return _public_urls(settings, publishing.list_publications(conn, workspace_id))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_publication(workspace_id: UUID, body: PublishBody, settings: SettingsDep, ctx: ManageCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            row = publishing.create_publication(conn, settings, workspace_id, str(ctx.user["id"]),
                                                kind=body.kind, title=body.title, report_id=body.report_id,
                                                person_id=body.person_id, filters=body.filters)
        except ValueError as exc:
            raise _err(exc) from exc
        return _public_urls(settings, [{k: (str(v) if isinstance(v, UUID) else v) for k, v in row.items()
                                        if k in ("id", "kind", "slug", "status", "title")}])[0]


@router.post("/refresh")
def refresh_all(workspace_id: UUID, settings: SettingsDep, ctx: ManageCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return publishing.refresh_workspace(conn, settings, workspace_id, str(ctx.user["id"]))


@router.post("/{pub_id}/refresh")
def refresh_one(workspace_id: UUID, pub_id: UUID, settings: SettingsDep, ctx: ManageCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            row = publishing.republish(conn, settings, workspace_id, str(ctx.user["id"]), pub_id)
        except ValueError as exc:
            raise _err(exc) from exc
        return {"id": str(row["id"]), "status": row["status"], "snapshot_at": row["snapshot_at"]}


@router.post("/{pub_id}/status")
def set_status(workspace_id: UUID, pub_id: UUID, body: StatusBody, settings: SettingsDep, ctx: ManageCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            row = publishing.set_status(conn, workspace_id, str(ctx.user["id"]), pub_id, body.status)
        except ValueError as exc:
            raise _err(exc) from exc
        return {"id": str(row["id"]), "status": row["status"]}


@router.get("/{pub_id}/export")
def static_export(workspace_id: UUID, pub_id: UUID, settings: SettingsDep, ctx: ManageCtx) -> dict[str, Any]:
    """The self-contained files (JSON + HTML) to upload to existing website hosting."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            files = publishing.static_export(conn, workspace_id, pub_id)
        except ValueError as exc:
            raise _err(exc) from exc
        return {"files": files}
