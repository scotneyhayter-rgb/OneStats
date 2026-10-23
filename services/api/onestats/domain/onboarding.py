"""Guided, resumable onboarding workflow (deliverable 8).

The wizard state is stored as JSONB on an onboarding_draft (Super-Admin owned). Steps
collect organisation identity/type, name + unique identifier, branding (four colours +
accent), programs/competitions and the initial workspace administrator. Programs and
competitions are captured in the draft state now and provisioned by later phases;
activation creates the workspace, its branding, and the initial administrator membership.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit, permissions, workspaces


def start_draft(conn: Connection, created_by: UUID, template: str | None = None) -> UUID:
    return conn.execute(
        text(
            "INSERT INTO onboarding_draft(created_by, template) VALUES (:c, :t) RETURNING id"
        ),
        {"c": created_by, "t": template},
    ).scalar_one()


def get_draft(conn: Connection, draft_id: UUID) -> dict[str, Any] | None:
    row = conn.execute(
        text(
            "SELECT id, created_by, workspace_id, template, current_step, status, state "
            "FROM onboarding_draft WHERE id = :id"
        ),
        {"id": draft_id},
    ).mappings().first()
    return dict(row) if row else None


def save_draft(
    conn: Connection, draft_id: UUID, state_patch: dict[str, Any], current_step: int | None = None
) -> dict[str, Any]:
    updated = conn.execute(
        text(
            "UPDATE onboarding_draft "
            "SET state = state || CAST(:p AS jsonb), "
            "current_step = coalesce(:s, current_step), updated_at = now() "
            "WHERE id = :id AND status = 'in_progress' RETURNING id"
        ),
        {"p": json.dumps(state_patch), "s": current_step, "id": draft_id},
    ).first()
    if updated is None:
        raise ValueError("draft_not_active")
    return get_draft(conn, draft_id)


def activate_draft(conn: Connection, draft_id: UUID, actor_user_id: UUID) -> UUID:
    draft = get_draft(conn, draft_id)
    if draft is None:
        raise ValueError("draft_not_found")
    if draft["status"] != "in_progress":
        raise ValueError("draft_not_active")

    state = draft["state"] or {}
    org = state.get("organisation") or {}
    name = (org.get("name") or state.get("name") or "").strip()
    short_name = (org.get("short_name") or state.get("short_name") or "").strip()
    wtype = org.get("type") or state.get("type") or "club"
    if not name or not short_name:
        raise ValueError("missing_required_fields")

    # Creates the workspace, sets the workspace context, and audits.
    ws_id = workspaces.create_workspace(conn, name, short_name, wtype, actor_user_id)

    branding = state.get("branding") or {}
    conn.execute(
        text(
            "INSERT INTO branding(workspace_id, primary_colour, secondary_colour, "
            "third_colour, fourth_colour, accent_colour, tagline) "
            "VALUES (:w, :p, :s, :t, :f, :a, :tag)"
        ),
        {
            "w": ws_id,
            "p": branding.get("primary"),
            "s": branding.get("secondary"),
            "t": branding.get("third"),
            "f": branding.get("fourth"),
            "a": branding.get("accent"),
            "tag": org.get("tagline"),
        },
    )

    admin_user_id = state.get("admin_user_id")
    if admin_user_id:
        permissions.grant_role(conn, UUID(str(admin_user_id)), ws_id, "workspace_admin")

    conn.execute(
        text(
            "UPDATE onboarding_draft SET status = 'activated', workspace_id = :w, "
            "updated_at = now() WHERE id = :id"
        ),
        {"w": ws_id, "id": draft_id},
    )
    audit.write_audit(
        conn, ws_id, str(actor_user_id), "workspace.onboard.activate",
        entity="workspace", entity_id=str(ws_id),
    )
    return ws_id
