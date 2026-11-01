"""Append-only audit logging for security-sensitive actions (deliverable 33).

Writes are workspace-scoped: the caller must have set the workspace context so the row
is accepted by the audit_log RLS policy (WITH CHECK on workspace_id). before/after are
stored as JSONB. Never log secrets or raw personal data in these payloads.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection


def write_audit(
    conn: Connection,
    workspace_id: UUID,
    actor: str | None,
    action: str,
    entity: str | None = None,
    entity_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    *,
    actor_role: str | None = None,
    effective_permission: str | None = None,
    reason: str | None = None,
    request_id: str | None = None,
    acting_as_super_admin: bool = False,
) -> None:
    """Append one audit row. `actor` is always the REAL authenticated user id — a Super Admin
    operating inside a workspace is recorded as themselves (never impersonating the local admin),
    with `acting_as_super_admin=True`. The role/permission/reason/request-id columns (Part 6) are
    optional so existing callers keep working; mutating role-gated endpoints should pass them."""
    conn.execute(
        text(
            "INSERT INTO audit_log(workspace_id, actor, action, entity, entity_id, before, after, "
            "actor_role, effective_permission, reason, request_id, acting_as_super_admin) "
            "VALUES (:w, :actor, :action, :entity, :eid, "
            "CAST(:before AS jsonb), CAST(:after AS jsonb), "
            ":role, :perm, :reason, :rid, :sa)"
        ),
        {
            "w": workspace_id,
            "actor": actor,
            "action": action,
            "entity": entity,
            "eid": entity_id,
            # default=str keeps non-JSON-native values (UUID, date, datetime) serialisable.
            "before": json.dumps(before, default=str) if before is not None else None,
            "after": json.dumps(after, default=str) if after is not None else None,
            "role": actor_role,
            "perm": effective_permission,
            "reason": reason,
            "rid": request_id,
            "sa": acting_as_super_admin,
        },
    )
