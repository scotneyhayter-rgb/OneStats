"""Research tasks & work queues (Phase 10, Stage 10.14).

A research task is a unit of work — usually created from a gap or a timeline drill-down — with a scope,
priority, assignee and status. Tasks belong to a workspace and optionally to a project, so several
authorised researchers can progress a project's outstanding questions. Every change is audited.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

STATUS = ("open", "in_progress", "resolved", "dismissed")


def _j(v: Any) -> str | None:
    return None if v is None else json.dumps(v)


def create_task(conn: Connection, workspace_id: UUID, actor: str, *, title: str,
                description: str | None = None, project_id: UUID | None = None, gap_kind: str | None = None,
                scope: Any = None, priority: int = 0, assigned_to: str | None = None) -> dict[str, Any]:
    if not (title or "").strip():
        raise ValueError("title_required")
    tid = conn.execute(
        text("INSERT INTO research_task(workspace_id, project_id, title, description, gap_kind, scope, "
             "priority, assigned_to, created_by) VALUES (:w, :p, :t, :d, :gk, CAST(:sc AS jsonb), :pr, :a, :by) "
             "RETURNING id"),
        {"w": workspace_id, "p": project_id, "t": title, "d": description, "gk": gap_kind, "sc": _j(scope),
         "pr": priority, "a": assigned_to, "by": actor},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "research.task_created", entity="research_task",
                      entity_id=str(tid), after={"title": title, "gap_kind": gap_kind})
    return get_task(conn, tid)


def get_task(conn: Connection, task_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text("SELECT * FROM research_task WHERE id = :id"), {"id": task_id}).mappings().first()
    return dict(r) if r else None


def list_tasks(conn: Connection, workspace_id: UUID, *, project_id: UUID | None = None,
               status: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM research_task WHERE workspace_id = :w"
    params: dict[str, Any] = {"w": workspace_id}
    if project_id is not None:
        sql += " AND project_id = :p"
        params["p"] = project_id
    if status is not None:
        sql += " AND status = :st"
        params["st"] = status
    sql += " ORDER BY priority DESC, created_at"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def update_task(conn: Connection, workspace_id: UUID, actor: str, task_id: UUID, *, title: str | None = None,
                description: str | None = None, priority: int | None = None, assigned_to: str | None = None,
                status: str | None = None) -> dict[str, Any]:
    if get_task(conn, task_id) is None:
        raise ValueError("task_not_found")
    if status is not None and status not in STATUS:
        raise ValueError("invalid_status")
    sets, params = [], {"id": task_id}
    for col, val in (("title", title), ("description", description), ("priority", priority),
                     ("assigned_to", assigned_to), ("status", status)):
        if val is not None:
            sets.append(f"{col} = :{col}")
            params[col] = val
    if status in ("resolved", "dismissed"):
        sets.append("resolved_at = now()")
    if sets:
        sets.append("updated_at = now()")
        conn.execute(text(f"UPDATE research_task SET {', '.join(sets)} WHERE id = :id"), params)
        audit.write_audit(conn, workspace_id, actor, "research.task_updated", entity="research_task",
                          entity_id=str(task_id), after={k: params[k] for k in params if k != "id"})
    return get_task(conn, task_id)
