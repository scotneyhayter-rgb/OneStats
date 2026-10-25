"""Saved Report Builder configurations (Phase 12, Stage 12.17).

Persist, list, reopen, edit and delete report definitions. A saved report is private to its creator
unless marked shared (then read-only to other workspace members). Only parameters are stored, so a
shared definition exposes no private data. Owner-only edit/delete; audited.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit


def _j(v: Any) -> str | None:
    return None if v is None else json.dumps(v)


def create(conn: Connection, workspace_id: UUID, actor: str, *, name: str, report: str,
           config: dict[str, Any] | None = None, shared: bool = False) -> dict[str, Any]:
    if not (name or "").strip():
        raise ValueError("name_required")
    if not (report or "").strip():
        raise ValueError("report_required")
    existing = conn.execute(
        text("SELECT id FROM saved_report WHERE workspace_id = :w AND created_by = :by AND name = :n"),
        {"w": workspace_id, "by": actor, "n": name},
    ).scalar_one_or_none()
    if existing is not None:
        raise ValueError("name_exists")
    rid = conn.execute(
        text("INSERT INTO saved_report(workspace_id, name, report, config, shared, created_by) "
             "VALUES (:w, :n, :r, CAST(:c AS jsonb), :sh, :by) RETURNING id"),
        {"w": workspace_id, "n": name, "r": report, "c": _j(config), "sh": shared, "by": actor},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "stats.saved_report_created", entity="saved_report",
                      entity_id=str(rid), after={"name": name, "report": report})
    return get(conn, rid)


def get(conn: Connection, report_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text("SELECT * FROM saved_report WHERE id = :id"), {"id": report_id}).mappings().first()
    return dict(r) if r else None


def list_reports(conn: Connection, workspace_id: UUID, actor: str) -> list[dict[str, Any]]:
    """The caller's own saved reports plus any shared in the workspace."""
    rows = conn.execute(
        text("SELECT * FROM saved_report WHERE workspace_id = :w AND (created_by = :by OR shared = true) "
             "ORDER BY name"),
        {"w": workspace_id, "by": actor},
    ).mappings().all()
    return [dict(r) for r in rows]


def update(conn: Connection, workspace_id: UUID, actor: str, report_id: UUID, *, name: str | None = None,
           config: dict[str, Any] | None = None, shared: bool | None = None) -> dict[str, Any]:
    cur = get(conn, report_id)
    if cur is None:
        raise ValueError("report_not_found")
    if cur["created_by"] != actor:
        raise ValueError("not_owner")   # only the owner may edit a saved report
    sets, params = [], {"id": report_id}
    if name is not None:
        sets.append("name = :name")
        params["name"] = name
    if config is not None:
        sets.append("config = CAST(:config AS jsonb)")
        params["config"] = _j(config)
    if shared is not None:
        sets.append("shared = :shared")
        params["shared"] = shared
    if sets:
        sets.append("updated_at = now()")
        conn.execute(text(f"UPDATE saved_report SET {', '.join(sets)} WHERE id = :id"), params)
        audit.write_audit(conn, workspace_id, actor, "stats.saved_report_updated", entity="saved_report",
                          entity_id=str(report_id), after={k: params[k] for k in params if k != "id"})
    return get(conn, report_id)


def delete(conn: Connection, workspace_id: UUID, actor: str, report_id: UUID) -> bool:
    cur = get(conn, report_id)
    if cur is None:
        return False
    if cur["created_by"] != actor:
        raise ValueError("not_owner")   # only the owner may delete a saved report
    conn.execute(text("DELETE FROM saved_report WHERE id = :id"), {"id": report_id})
    audit.write_audit(conn, workspace_id, actor, "stats.saved_report_deleted", entity="saved_report",
                      entity_id=str(report_id), after={"name": cur["name"]})
    return True
