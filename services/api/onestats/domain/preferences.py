"""Per-user preferences (Part 15) — e.g. dashboard customisation.

A small JSONB bag per (user, optional workspace, namespace). Must be called inside a user-scoped
transaction (``user_transaction``) so the user_preference RLS policy limits rows to the caller.
Preferences are a convenience layer only: they never gate permissions and must never be used to
hide security/admin warnings (that is enforced in the UI).
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection


def get_preferences(conn: Connection, user_id: UUID, namespace: str,
                    workspace_id: UUID | None = None) -> dict[str, Any]:
    row = conn.execute(
        text("SELECT prefs FROM user_preference WHERE app_user_id = :u AND namespace = :ns "
             "AND workspace_id IS NOT DISTINCT FROM :w"),
        {"u": user_id, "ns": namespace, "w": workspace_id},
    ).scalar_one_or_none()
    return dict(row) if row else {}


def set_preferences(conn: Connection, user_id: UUID, namespace: str, prefs: dict[str, Any],
                    workspace_id: UUID | None = None) -> dict[str, Any]:
    if not isinstance(prefs, dict):
        raise ValueError("prefs_must_be_object")
    # distinct upsert targets for the two partial unique indexes (global vs workspace-scoped)
    if workspace_id is None:
        conn.execute(
            text("INSERT INTO user_preference(app_user_id, namespace, prefs, updated_at) "
                 "VALUES (:u, :ns, CAST(:p AS jsonb), now()) "
                 "ON CONFLICT (app_user_id, namespace) WHERE workspace_id IS NULL "
                 "DO UPDATE SET prefs = EXCLUDED.prefs, updated_at = now()"),
            {"u": user_id, "ns": namespace, "p": json.dumps(prefs)},
        )
    else:
        conn.execute(
            text("INSERT INTO user_preference(app_user_id, workspace_id, namespace, prefs, updated_at) "
                 "VALUES (:u, :w, :ns, CAST(:p AS jsonb), now()) "
                 "ON CONFLICT (app_user_id, workspace_id, namespace) WHERE workspace_id IS NOT NULL "
                 "DO UPDATE SET prefs = EXCLUDED.prefs, updated_at = now()"),
            {"u": user_id, "w": workspace_id, "ns": namespace, "p": json.dumps(prefs)},
        )
    return get_preferences(conn, user_id, namespace, workspace_id)
