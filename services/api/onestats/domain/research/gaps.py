"""Research Gaps & coverage analysis (Phase 10, Stage 10.13).

Surfaces where historical research effort is most valuable — missing scorecards, unknown results,
unknown dates, unverified claims, disputed records — from REAL data, never guessed. Each category gives
a count plus a sample of affected matches so a researcher can open a gap and start a targeted task.
Research coverage is tracked separately from cricket activity (an unsearched period is not 'complete').
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

_SAMPLE = 25


def coverage_gaps(conn: Connection, workspace_id: UUID) -> dict[str, Any]:
    def _cat(where: str) -> dict[str, Any]:
        n = conn.execute(text(f"SELECT count(*) FROM match m WHERE m.workspace_id = :w AND ({where})"),
                         {"w": workspace_id}).scalar_one()
        sample = conn.execute(
            text(f"SELECT m.id, m.match_date, m.round FROM match m WHERE m.workspace_id = :w AND ({where}) "
                 "ORDER BY m.match_date NULLS LAST LIMIT :lim"),
            {"w": workspace_id, "lim": _SAMPLE},
        ).mappings().all()
        return {"count": n, "sample": [{"match_id": str(r["id"]),
                                        "match_date": r["match_date"].isoformat() if r["match_date"] else None,
                                        "round": r["round"]} for r in sample]}

    no_scorecard = "NOT EXISTS (SELECT 1 FROM innings i WHERE i.match_id = m.id)"
    unverified_claims = conn.execute(
        text("SELECT count(*) FROM field_provenance WHERE workspace_id = :w AND status = 'claimed'"),
        {"w": workspace_id}).scalar_one()
    return {
        "matches_missing_scorecard": _cat(no_scorecard),
        "matches_without_result": _cat("m.result_type IS NULL OR m.result_type = 'unknown'"),
        "matches_unknown_date": _cat("m.match_date IS NULL"),
        "draft_scorecards": _cat("m.approval_status = 'draft'"),
        "disputed_records": _cat("m.approval_status = 'disputed'"),
        "unverified_claims": {"count": unverified_claims},
    }
