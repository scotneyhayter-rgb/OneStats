"""Workspace lifecycle + membership resolution (deliverables 5, 6, 8).

Writes set the workspace context and are audited. Duplicate workspace identifiers
(short_name) are rejected (also enforced by a unique index). "My workspaces" uses the
user context so a user sees only workspaces they belong to; the Super Administrator sees
all.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.db.workspace import set_workspace
from onestats.domain import audit

_SELECT = "id, name, short_name, type, status, score_format, created_at"
SCORE_FORMATS = ("au", "en")


def short_name_taken(conn: Connection, short_name: str, exclude_id: UUID | None = None) -> bool:
    sql = "SELECT 1 FROM workspace WHERE lower(short_name) = lower(:s)"
    params: dict[str, Any] = {"s": short_name}
    if exclude_id is not None:
        sql += " AND id <> :id"
        params["id"] = exclude_id
    return conn.execute(text(sql), params).first() is not None


def get_workspace(conn: Connection, workspace_id: UUID) -> dict[str, Any] | None:
    row = conn.execute(
        text(f"SELECT {_SELECT} FROM workspace WHERE id = :id"), {"id": workspace_id}
    ).mappings().first()
    return dict(row) if row else None


def create_workspace(
    conn: Connection, name: str, short_name: str, wtype: str, actor_user_id: UUID
) -> UUID:
    name = (name or "").strip()
    short_name = (short_name or "").strip()
    if not name or not short_name:
        raise ValueError("missing_required_fields")
    if wtype not in ("club", "association", "international", "custom"):
        raise ValueError("invalid_type")
    if short_name_taken(conn, short_name):
        raise ValueError("duplicate_identifier")
    ws_id = conn.execute(
        text(
            "INSERT INTO workspace(name, short_name, type) VALUES (:n, :s, :t) RETURNING id"
        ),
        {"n": name, "s": short_name, "t": wtype},
    ).scalar_one()
    set_workspace(conn, ws_id)
    audit.write_audit(
        conn, ws_id, str(actor_user_id), "workspace.create", entity="workspace",
        entity_id=str(ws_id), after={"name": name, "short_name": short_name, "type": wtype},
    )
    return ws_id


def update_workspace(
    conn: Connection,
    workspace_id: UUID,
    actor_user_id: UUID,
    name: str | None = None,
    short_name: str | None = None,
    status: str | None = None,
    score_format: str | None = None,
) -> dict[str, Any]:
    before = get_workspace(conn, workspace_id)
    if before is None:
        raise ValueError("workspace_not_found")
    if short_name and short_name_taken(conn, short_name, exclude_id=workspace_id):
        raise ValueError("duplicate_identifier")
    if score_format is not None and score_format not in SCORE_FORMATS:
        raise ValueError("invalid_score_format")
    set_workspace(conn, workspace_id)
    conn.execute(
        text(
            "UPDATE workspace SET name = coalesce(:n, name), "
            "short_name = coalesce(:s, short_name), status = coalesce(:st, status), "
            "score_format = coalesce(:sf, score_format) "
            "WHERE id = :id"
        ),
        {"n": name, "s": short_name, "st": status, "sf": score_format, "id": workspace_id},
    )
    after = get_workspace(conn, workspace_id)
    audit.write_audit(
        conn, workspace_id, str(actor_user_id), "workspace.update", entity="workspace",
        entity_id=str(workspace_id), before=before, after=after,
    )
    return after


def list_for_user(
    conn: Connection, user_id: UUID, is_super_admin: bool
) -> list[dict[str, Any]]:
    """Workspaces the user may access. Super Admin: all. Others: memberships (requires the
    user context GUC to be set so own memberships are visible across workspaces)."""
    if is_super_admin:
        rows = conn.execute(
            text(f"SELECT {_SELECT} FROM workspace ORDER BY name")
        ).mappings().all()
        return [dict(r) | {"roles": ["super_admin"]} for r in rows]
    rows = conn.execute(
        text(
            "SELECT w.id, w.name, w.short_name, w.type, w.status, w.created_at, "
            "array_agg(r.key ORDER BY r.key) AS roles "
            "FROM app_user_workspace_role m "
            "JOIN workspace w ON w.id = m.workspace_id "
            "JOIN role r ON r.id = m.role_id "
            "WHERE m.app_user_id = :u "
            "GROUP BY w.id, w.name, w.short_name, w.type, w.status, w.created_at "
            "ORDER BY w.name"
        ),
        {"u": user_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def user_is_member(conn: Connection, user_id: UUID, workspace_id: UUID) -> bool:
    return conn.execute(
        text(
            "SELECT 1 FROM app_user_workspace_role "
            "WHERE app_user_id = :u AND workspace_id = :w"
        ),
        {"u": user_id, "w": workspace_id},
    ).first() is not None


def list_members(conn: Connection, workspace_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT u.id AS user_id, u.username, u.display_name, "
            "array_agg(r.key ORDER BY r.key) AS roles "
            "FROM app_user_workspace_role m "
            "JOIN app_user u ON u.id = m.app_user_id "
            "JOIN role r ON r.id = m.role_id "
            "WHERE m.workspace_id = :w "
            "GROUP BY u.id, u.username, u.display_name ORDER BY u.username"
        ),
        {"w": workspace_id},
    ).mappings().all()
    return [dict(r) for r in rows]
