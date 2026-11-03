"""Scheduled-task / Update-Management endpoints (Parts I & J).

Backs the workspace's Update Management section: list the recurring task(s), their genuine run history
(with each run's scheduled-vs-actual time and whether it was a catch-up), run now, and pause/resume or
enable/disable. All figures come straight from the database — nothing here fabricates a run or a
result. Managing tasks requires ``workspace.manage``; workspace-scoped (FORCE RLS) and audited.
"""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain.scheduler import tasks

router = APIRouter(prefix="/workspaces/{workspace_id}/scheduler", tags=["scheduler"])

Ctx = Annotated[RequestContext, Depends(require_permission("workspace.manage"))]


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


class ToggleBody(BaseModel):
    value: bool


@router.get("/tasks")
def list_tasks(workspace_id: UUID, settings: SettingsDep, ctx: Ctx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return tasks.list_tasks(conn, workspace_id)


@router.get("/tasks/{task_id}/runs")
def list_runs(workspace_id: UUID, task_id: UUID, settings: SettingsDep, ctx: Ctx,
              limit: int = 50) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return tasks.list_runs(conn, workspace_id, task_id=task_id, limit=min(limit, 200))


@router.post("/tasks/{task_id}/run-now")
def run_now(workspace_id: UUID, task_id: UUID, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    actor = str(ctx.user["id"])
    try:
        with workspace_transaction(_engine(settings), workspace_id) as conn:
            return tasks.run_now(conn, workspace_id, actor, task_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND if str(exc) == "task_not_found"
                            else status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/tasks/{task_id}/pause")
def pause(workspace_id: UUID, task_id: UUID, body: ToggleBody, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    actor = str(ctx.user["id"])
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return tasks.set_paused(conn, workspace_id, actor, task_id, body.value)


@router.post("/tasks/{task_id}/enable")
def enable(workspace_id: UUID, task_id: UUID, body: ToggleBody, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    actor = str(ctx.user["id"])
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return tasks.set_enabled(conn, workspace_id, actor, task_id, body.value)
