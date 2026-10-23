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
) -> None:
    conn.execute(
        text(
            "INSERT INTO audit_log(workspace_id, actor, action, entity, entity_id, before, after) "
            "VALUES (:w, :actor, :action, :entity, :eid, "
            "CAST(:before AS jsonb), CAST(:after AS jsonb))"
        ),
        {
            "w": workspace_id,
            "actor": actor,
            "action": action,
            "entity": entity,
            "eid": entity_id,
            "before": json.dumps(before) if before is not None else None,
            "after": json.dumps(after) if after is not None else None,
        },
    )
