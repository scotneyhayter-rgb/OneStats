"""Research Centre dashboard (Phase 10, Stage 10.1).

Real, database-backed counts for the research dashboard — never fabricated. Research-specific figures
come from the Phase 10 tables; verification/scorecard figures reuse the Phase 7 ``match.approval_status``
machine; conflict signals reuse Phase 9 discovery. Unknown/absent is reported as a genuine zero, not an
assumed value.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain.research import sources as rsources


def dashboard_summary(conn: Connection, workspace_id: UUID) -> dict[str, Any]:
    def _scalar(sql: str) -> int:
        return conn.execute(text(sql), {"w": workspace_id}).scalar_one()

    return {
        # Research projects
        "projects_active": _scalar("SELECT count(*) FROM research_project WHERE workspace_id = :w AND status = 'active'"),
        "projects_total": _scalar("SELECT count(*) FROM research_project WHERE workspace_id = :w"),
        # Sources (Source Library)
        "sources_total": _scalar("SELECT count(*) FROM research_source WHERE workspace_id = :w"),
        "sources_recent": [
            {"id": str(s["id"]), "title": s["title"], "source_type": s["source_type"],
             "created_at": s["created_at"].isoformat() if s.get("created_at") else None}
            for s in rsources.list_sources(conn, workspace_id, limit=5)
        ],
        # Matches under investigation = canonical matches with at least one research source attached
        "matches_under_investigation": _scalar(
            "SELECT count(DISTINCT match_id) FROM research_source_match WHERE workspace_id = :w"),
        # Scorecard / verification state (reuse Phase 7 approval machine)
        "draft_scorecards": _scalar("SELECT count(*) FROM match WHERE workspace_id = :w AND approval_status = 'draft'"),
        "awaiting_verification": _scalar(
            "SELECT count(*) FROM match WHERE workspace_id = :w AND approval_status = 'awaiting_approval'"),
        "disputed": _scalar("SELECT count(*) FROM match WHERE workspace_id = :w AND approval_status = 'disputed'"),
        "verified": _scalar("SELECT count(*) FROM match WHERE workspace_id = :w AND approval_status = 'approved'"),
        # Conflicting evidence (Phase 9 discovery conflicts pending review + disputed research notes)
        "conflicting_evidence": _scalar(
            "SELECT (SELECT count(*) FROM discovery_item WHERE workspace_id = :w "
            "AND classification = 'conflicting' AND status = 'pending_review') "
            "+ (SELECT count(*) FROM research_note WHERE workspace_id = :w AND evidence_class = 'disputed')"),
        # Research gaps / tasks
        "open_tasks": _scalar(
            "SELECT count(*) FROM research_task WHERE workspace_id = :w AND status IN ('open','in_progress')"),
        "notes_total": _scalar("SELECT count(*) FROM research_note WHERE workspace_id = :w"),
    }
