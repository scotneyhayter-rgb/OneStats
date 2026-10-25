"""Workspace dashboard summary (home-page command centre).

Real, database-backed counts and recent activity for the workspace home page — never fabricated. Every
figure comes from an existing table; empty workspaces return genuine zeros. Queries are simple COUNTs and
a small recent-activity read, kept cheap so they never slow startup. Statistics/approval/provenance rules
are not touched here — this module only reads.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

# Friendly category for a recent-activity row, by audit action prefix.
_ACTIVITY = {
    "import": "Import",
    "autosync": "AutoSync",
    "research": "Research",
    "media": "Media",
    "match": "Scorecard",
    "person": "People",
}


def _category(action: str) -> str:
    prefix = (action or "").split(".", 1)[0]
    return _ACTIVITY.get(prefix, prefix or "Activity")


def workspace_dashboard(conn: Connection, workspace_id: UUID) -> dict[str, Any]:
    def _n(sql: str) -> int:
        return conn.execute(text(sql), {"w": workspace_id}).scalar_one()

    totals = {
        "matches": _n("SELECT count(*) FROM match WHERE workspace_id = :w"),
        "players": _n("SELECT count(*) FROM person WHERE workspace_id = :w"),
        "approved_scorecards": _n("SELECT count(*) FROM match WHERE workspace_id = :w "
                                  "AND approval_status IN ('approved','verified_partial')"),
        "seasons": _n("SELECT count(*) FROM season WHERE workspace_id = :w"),
        "competitions": _n("SELECT count(*) FROM competition WHERE workspace_id = :w"),
        "organisations": _n("SELECT count(*) FROM organisation WHERE workspace_id = :w"),
        "media_assets": _n("SELECT count(*) FROM media_asset WHERE workspace_id = :w"),
    }
    attention = {
        "scorecards_awaiting_approval": _n("SELECT count(*) FROM match WHERE workspace_id = :w "
                                           "AND approval_status = 'awaiting_approval'"),
        "possible_duplicate_matches": _n("SELECT count(*) FROM discovery_item WHERE workspace_id = :w "
                                         "AND classification = 'possible_duplicate' AND status = 'pending_review'"),
        "research_conflicts": _n(
            "SELECT (SELECT count(*) FROM discovery_item WHERE workspace_id = :w AND classification = 'conflicting' "
            "AND status = 'pending_review') + (SELECT count(*) FROM match WHERE workspace_id = :w "
            "AND approval_status = 'disputed')"),
        "failed_autosync_jobs": _n("SELECT count(*) FROM sync_job WHERE workspace_id = :w AND status = 'failed'"),
    }
    research = {
        "projects_active": _n("SELECT count(*) FROM research_project WHERE workspace_id = :w AND status = 'active'"),
        "incomplete_scorecards": _n("SELECT count(*) FROM match WHERE workspace_id = :w AND approval_status = 'draft'"),
        "open_research_tasks": _n("SELECT count(*) FROM research_task WHERE workspace_id = :w "
                                  "AND status IN ('open','in_progress')"),
        "sources": _n("SELECT count(*) FROM research_source WHERE workspace_id = :w"),
    }
    # leading performers from the one statistics engine (approved data only; empty on a new workspace)
    from onestats.domain.stats import engine as stats_engine
    f = {"workspace_id": workspace_id}
    top_bat = stats_engine.batting_leaders(conn, f, order_by="runs", limit=1)
    top_bowl = stats_engine.bowling_leaders(conn, f, order_by="wickets", limit=1)
    leaders = {
        "leading_run_scorer": ({"person_id": top_bat[0]["subject_id"], "runs": top_bat[0]["runs"]}
                               if top_bat and top_bat[0]["runs"] else None),
        "leading_wicket_taker": ({"person_id": top_bowl[0]["subject_id"], "wickets": top_bowl[0]["wickets"]}
                                 if top_bowl and top_bowl[0]["wickets"] else None),
    }

    recent = [
        {"action": r["action"], "category": _category(r["action"]), "entity": r["entity"],
         "at": r["at"].isoformat() if r["at"] else None, "actor": r["actor"]}
        for r in conn.execute(
            text("SELECT action, entity, actor, at FROM audit_log WHERE workspace_id = :w "
                 "ORDER BY at DESC LIMIT 12"), {"w": workspace_id}).mappings().all()
    ]
    return {
        "totals": totals,
        "attention": attention,
        "research": research,
        "leaders": leaders,
        "recent_activity": recent,
        "is_empty": totals["matches"] == 0 and totals["players"] == 0 and totals["organisations"] == 0,
    }
