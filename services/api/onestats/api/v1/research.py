"""Research Centre API (Phase 10). Workspace-scoped, gated by ``research.manage``, audited.

Research projects, the Source Library and a real-data dashboard. Historical reconstruction reuses the
Phase 6 scorecard tables and Phase 7 approval; nothing here enters official statistics without the
existing approval workflow.
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
from onestats.domain.research import dashboard, projects, sources

router = APIRouter(prefix="/workspaces/{workspace_id}/research", tags=["research"])
Ctx = Annotated[RequestContext, Depends(require_permission("research.manage"))]

_ERRORS = {
    "title_required": status.HTTP_400_BAD_REQUEST,
    "invalid_status": status.HTTP_400_BAD_REQUEST,
    "invalid_source_type": status.HTTP_400_BAD_REQUEST,
    "invalid_date_precision": status.HTTP_400_BAD_REQUEST,
    "invalid_ocr_status": status.HTTP_400_BAD_REQUEST,
    "project_not_found": status.HTTP_404_NOT_FOUND,
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


class ProjectCreate(BaseModel):
    title: str
    description: str | None = None
    scope: dict[str, Any] | None = None
    owner: str | None = None
    status: str = Field(default="active", pattern="^(active|paused|completed|archived)$")


class ProjectUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    scope: dict[str, Any] | None = None
    owner: str | None = None
    status: str | None = Field(default=None, pattern="^(active|paused|completed|archived)$")


class SourceCreate(BaseModel):
    title: str
    source_type: str
    publication: str | None = None
    author: str | None = None
    publication_date: date | None = None
    publication_date_precision: str | None = Field(
        default=None, pattern="^(exact|month|year|approximate|range|unknown)$")
    edition: str | None = None
    page_ref: str | None = None
    original_url: str | None = None
    archive_ref: str | None = None
    source_identifier: str | None = None
    language: str | None = None
    location: str | None = None
    copyright_status: str | None = None
    usage_restrictions: str | None = None
    date_accessed: date | None = None
    notes: str | None = None


class LinkMatch(BaseModel):
    match_id: UUID
    role: str | None = None


@router.get("/dashboard")
def get_dashboard(workspace_id: UUID, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return dashboard.dashboard_summary(conn, workspace_id)


@router.get("/projects")
def list_projects(workspace_id: UUID, settings: SettingsDep, ctx: Ctx,
                  status_filter: str | None = None) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_s(r) for r in projects.list_projects(conn, workspace_id, status=status_filter)]


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(workspace_id: UUID, body: ProjectCreate, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(projects.create_project(conn, workspace_id, str(ctx.user["id"]), **body.model_dump()))
        except ValueError as exc:
            raise _err(exc) from exc


@router.get("/projects/{project_id}")
def get_project(workspace_id: UUID, project_id: UUID, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        proj = projects.get_project(conn, project_id)
        if proj is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "project_not_found")
        return _s(proj)


@router.patch("/projects/{project_id}")
def update_project(workspace_id: UUID, project_id: UUID, body: ProjectUpdate,
                   settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(projects.update_project(conn, workspace_id, str(ctx.user["id"]), project_id,
                                              **body.model_dump(exclude_none=True)))
        except ValueError as exc:
            raise _err(exc) from exc


@router.get("/sources")
def list_sources(workspace_id: UUID, settings: SettingsDep, ctx: Ctx,
                 source_type: str | None = None) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_s(r) for r in sources.list_sources(conn, workspace_id, source_type=source_type)]


@router.post("/sources", status_code=status.HTTP_201_CREATED)
def create_source(workspace_id: UUID, body: SourceCreate, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(sources.create_source(conn, workspace_id, str(ctx.user["id"]), **body.model_dump()))
        except ValueError as exc:
            raise _err(exc) from exc


@router.get("/sources/{source_id}")
def get_source(workspace_id: UUID, source_id: UUID, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        src = sources.get_source(conn, source_id)
        if src is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "source_not_found")
        return _s(src)


@router.post("/sources/{source_id}/link")
def link_source_match(workspace_id: UUID, source_id: UUID, body: LinkMatch,
                      settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return _s(sources.link_match(conn, workspace_id, str(ctx.user["id"]), source_id, body.match_id,
                                     role=body.role))


@router.get("/matches/{match_id}/sources")
def match_sources(workspace_id: UUID, match_id: UUID, settings: SettingsDep, ctx: Ctx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_s(r) for r in sources.list_sources_for_match(conn, workspace_id, match_id)]
