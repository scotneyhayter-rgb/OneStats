"""AutoSync API (Phase 9). Workspace-scoped, gated by ``import.manage``, audited.

Configure sources, run Sync Now (a real job), review discoveries (accept/reject/bulk), run historical
discovery, and read a real-data dashboard. Imported matches remain draft (Phase 7 approval governs
official statistics).
"""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain.autosync import discovery, jobs, service, sources
from onestats.domain.autosync.connectors import catalog

router = APIRouter(prefix="/workspaces/{workspace_id}/autosync", tags=["autosync"])
Ctx = Annotated[RequestContext, Depends(require_permission("import.manage"))]

_ERRORS = {
    "source_name_exists": status.HTTP_409_CONFLICT,
    "duplicate_active_job": status.HTTP_409_CONFLICT,
    "invalid_reliability": status.HTTP_400_BAD_REQUEST,
    "invalid_bulk_action": status.HTTP_400_BAD_REQUEST,
    "item_not_found": status.HTTP_404_NOT_FOUND,
}


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


def _err(exc: ValueError) -> HTTPException:
    return HTTPException(_ERRORS.get(str(exc), status.HTTP_400_BAD_REQUEST), str(exc))


def _s(d: dict[str, Any]) -> dict[str, Any]:
    return {k: (str(v) if isinstance(v, UUID) else v) for k, v in d.items()}


class SourceCreate(BaseModel):
    connector_id: str
    name: str
    provider: str | None = None
    access_method: str | None = None
    endpoint: str | None = None
    auth_required: bool = False
    credentials_ref: str | None = None
    countries: list[str] | None = None
    formats: list[str] | None = None
    enabled: bool = True
    notes: str | None = None


class SyncNow(BaseModel):
    source_system: str
    kind: str = Field(default="manual", pattern="^(new|updated|historical|manual)$")


class HistoryRun(BaseModel):
    source_system: str
    scopes: list[dict[str, Any]] = Field(default_factory=list)


class BulkReview(BaseModel):
    item_ids: list[UUID]
    action: str = Field(pattern="^(accept|reject)$")
    notes: str | None = None


@router.get("/connectors")
def list_connectors(workspace_id: UUID, settings: SettingsDep, ctx: Ctx) -> list[dict[str, Any]]:
    return catalog.describe()


@router.get("/sources")
def list_sources(workspace_id: UUID, settings: SettingsDep, ctx: Ctx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_s(r) for r in sources.list_sources(conn, workspace_id)]


@router.post("/sources", status_code=status.HTTP_201_CREATED)
def create_source(workspace_id: UUID, body: SourceCreate, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(sources.register_source(conn, workspace_id, str(ctx.user["id"]), **body.model_dump()))
        except ValueError as exc:
            raise _err(exc) from exc


@router.patch("/sources/{source_id}")
def update_source(workspace_id: UUID, source_id: UUID, enabled: bool, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return _s(sources.set_enabled(conn, workspace_id, str(ctx.user["id"]), source_id, enabled))


@router.post("/sync-now")
def sync_now(workspace_id: UUID, body: SyncNow, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            out = service.sync_now(conn, workspace_id, str(ctx.user["id"]),
                                   source_system=body.source_system, kind=body.kind)
            return {"ran": out["ran"], "job": _s(out["job"])}
        except ValueError as exc:
            raise _err(exc) from exc


@router.post("/discover-history")
def discover_history(workspace_id: UUID, body: HistoryRun, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            job = jobs.create_job(conn, workspace_id, str(ctx.user["id"]), source_system=body.source_system,
                                  kind="historical", progress={"scopes": body.scopes})
            claimed = jobs.claim_next_job(conn, workspace_id, str(ctx.user["id"]))
            if claimed:
                jobs.run_job(conn, workspace_id, str(ctx.user["id"]), claimed)
            return {"job_id": str(job["id"])}
        except ValueError as exc:
            raise _err(exc) from exc


@router.get("/jobs")
def list_jobs(workspace_id: UUID, settings: SettingsDep, ctx: Ctx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_s(r) for r in jobs.list_jobs(conn, workspace_id)]


@router.get("/review")
def review_queue(workspace_id: UUID, settings: SettingsDep, ctx: Ctx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_s(r) for r in discovery.list_items(conn, workspace_id, status="pending_review")]


@router.post("/review/{item_id}/accept")
def accept(workspace_id: UUID, item_id: UUID, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(discovery.accept_item(conn, workspace_id, str(ctx.user["id"]), item_id))
        except ValueError as exc:
            raise _err(exc) from exc


@router.post("/review/{item_id}/reject")
def reject(workspace_id: UUID, item_id: UUID, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return _s(discovery.reject_item(conn, workspace_id, str(ctx.user["id"]), item_id))


@router.post("/review/bulk")
def bulk(workspace_id: UUID, body: BulkReview, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return discovery.bulk_review(conn, workspace_id, str(ctx.user["id"]), body.item_ids,
                                         action=body.action, notes=body.notes)
        except ValueError as exc:
            raise _err(exc) from exc


@router.get("/coverage")
def coverage(workspace_id: UUID, settings: SettingsDep, ctx: Ctx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_s(r) for r in discovery.list_coverage(conn, workspace_id)]


@router.get("/dashboard")
def dashboard(workspace_id: UUID, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return service.dashboard_summary(conn, workspace_id)
