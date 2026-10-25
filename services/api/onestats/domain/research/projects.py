"""Research projects (Phase 10, Stage 10.1/10.14).

A research project scopes a line of historical research (club / competition / season / date range,
including historical aliases) with an owner and status. Projects group sources, notes and tasks and
later drive targeted discovery. Workspace-scoped (FORCE RLS); every change audited.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

STATUS = ("active", "paused", "completed", "archived")


def _j(v: Any) -> str | None:
    return None if v is None else json.dumps(v)


def create_project(conn: Connection, workspace_id: UUID, actor: str, *, title: str,
                   description: str | None = None, scope: Any = None, owner: str | None = None,
                   status: str = "active") -> dict[str, Any]:
    if status not in STATUS:
        raise ValueError("invalid_status")
    if not (title or "").strip():
        raise ValueError("title_required")
    pid = conn.execute(
        text("INSERT INTO research_project(workspace_id, title, description, scope, owner, status, created_by) "
             "VALUES (:w, :t, :d, CAST(:sc AS jsonb), :o, :st, :by) RETURNING id"),
        {"w": workspace_id, "t": title, "d": description, "sc": _j(scope), "o": owner, "st": status, "by": actor},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "research.project_created", entity="research_project",
                      entity_id=str(pid), after={"title": title, "status": status})
    return get_project(conn, pid)


def get_project(conn: Connection, project_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text("SELECT * FROM research_project WHERE id = :id"), {"id": project_id}).mappings().first()
    return dict(r) if r else None


def list_projects(conn: Connection, workspace_id: UUID, *, status: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM research_project WHERE workspace_id = :w"
    params: dict[str, Any] = {"w": workspace_id}
    if status is not None:
        sql += " AND status = :st"
        params["st"] = status
    sql += " ORDER BY updated_at DESC, created_at DESC"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def update_project(conn: Connection, workspace_id: UUID, actor: str, project_id: UUID, *,
                   title: str | None = None, description: str | None = None, scope: Any = None,
                   owner: str | None = None, status: str | None = None) -> dict[str, Any]:
    current = get_project(conn, project_id)
    if current is None:
        raise ValueError("project_not_found")
    if status is not None and status not in STATUS:
        raise ValueError("invalid_status")
    sets, params = [], {"id": project_id}
    for col, val, cast in (("title", title, None), ("description", description, None),
                           ("scope", scope, "jsonb"), ("owner", owner, None), ("status", status, None)):
        if val is not None:
            if cast == "jsonb":
                sets.append(f"{col} = CAST(:{col} AS jsonb)")
                params[col] = _j(val)
            else:
                sets.append(f"{col} = :{col}")
                params[col] = val
    if sets:
        sets.append("updated_at = now()")
        conn.execute(text(f"UPDATE research_project SET {', '.join(sets)} WHERE id = :id"), params)
        audit.write_audit(conn, workspace_id, actor, "research.project_updated", entity="research_project",
                          entity_id=str(project_id), after={k: params[k] for k in params if k != "id"})
    return get_project(conn, project_id)
