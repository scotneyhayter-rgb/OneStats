"""Platform ("All Workspaces") dashboard for the Super Administrator (Part 4).

A cross-workspace, read-only overview. **Workspace isolation is preserved**: per-workspace record
counts are gathered by setting the workspace context for each workspace in turn, so FORCE RLS stays
fully in effect — we never disable RLS and never use a bypass/owner role. Global registry tables
(workspace, app_user, session) are not workspace-scoped and are read directly.

All per-workspace totals are counts of **workspace records**: the same real-world match or player
can exist in more than one workspace, so the platform totals are deliberately labelled as workspace
record counts, not global-unique counts. No figure is fabricated; empty platforms return real zeros.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from onestats.db.workspace import workspace_transaction


def _ws_counts(engine: Engine, workspace_id: Any) -> dict[str, int]:
    """Record counts for a single workspace, read under that workspace's RLS context."""
    with workspace_transaction(engine, workspace_id) as conn:
        def n(sql: str) -> int:
            return int(conn.execute(text(sql)).scalar_one())

        return {
            "matches": n("SELECT count(*) FROM match"),
            "players": n("SELECT count(*) FROM person WHERE merged_into_id IS NULL"),
            "approved_scorecards": n(
                "SELECT count(*) FROM match WHERE approval_status IN ('approved','verified_partial')"
            ),
            "awaiting_approval": n("SELECT count(*) FROM match WHERE approval_status = 'awaiting_approval'"),
            "seasons": n("SELECT count(*) FROM season"),
            "members": n("SELECT count(DISTINCT app_user_id) FROM app_user_workspace_role"),
        }


def platform_dashboard(engine: Engine) -> dict[str, Any]:
    # --- global registry (not workspace-scoped; no RLS) ---
    with engine.begin() as conn:
        workspaces = [
            dict(r) for r in conn.execute(
                text("SELECT id, name, short_name, type, status, created_at FROM workspace ORDER BY name")
            ).mappings().all()
        ]
        users_total = int(conn.execute(text("SELECT count(*) FROM app_user")).scalar_one())
        users_active = int(conn.execute(
            text("SELECT count(*) FROM app_user WHERE status = 'active'")).scalar_one())
        super_admins = int(conn.execute(
            text("SELECT count(*) FROM app_user WHERE is_super_admin AND status = 'active'")).scalar_one())
        active_sessions = int(conn.execute(
            text("SELECT count(*) FROM session WHERE revoked_at IS NULL AND expires_at > now()")).scalar_one())
        # recent platform-level (account) activity — global admin_audit, no personal data in payload
        platform_activity = [
            {"action": r["action"], "actor": r["actor"], "target_user_id": str(r["target_user_id"]) if r["target_user_id"] else None,
             "at": r["at"].isoformat() if r["at"] else None}
            for r in conn.execute(
                text("SELECT action, actor, target_user_id, at FROM admin_audit ORDER BY at DESC LIMIT 15")
            ).mappings().all()
        ]

    # --- per-workspace record counts (each under its own RLS context) ---
    organisations: list[dict[str, Any]] = []
    totals = {"matches": 0, "players": 0, "approved_scorecards": 0, "awaiting_approval": 0,
              "seasons": 0, "members": 0}
    for w in workspaces:
        counts = _ws_counts(engine, w["id"])
        for k in totals:
            totals[k] += counts[k]
        organisations.append({
            "workspace_id": str(w["id"]),
            "name": w["name"],
            "short_name": w["short_name"],
            "type": w["type"],
            "status": w["status"],
            **counts,
        })

    return {
        # NB: workspace record counts, NOT global-unique — a match/player may appear in several workspaces.
        "summary": {
            "workspaces": len(workspaces),
            "active_workspaces": sum(1 for w in workspaces if w["status"] == "active"),
            "users_total": users_total,
            "users_active": users_active,
            "super_admins": super_admins,
            "workspace_match_records": totals["matches"],
            "workspace_player_records": totals["players"],
            "workspace_approved_scorecards": totals["approved_scorecards"],
            "workspace_awaiting_approval": totals["awaiting_approval"],
        },
        "totals_are_workspace_records": True,
        "organisations": organisations,
        "system_health": {
            "database_connected": True,
            "active_sessions": active_sessions,
            "super_admins": super_admins,
        },
        "platform_activity": platform_activity,
        "is_empty": len(workspaces) == 0,
    }
