"""Data integrity & historical completeness (Phase 12, Stage 12.18).

Surfaces where approved statistics rest on incomplete data, so reports can distinguish confirmed values
from known-minimums and flag records that need attention — never hiding or inventing anything. Includes
run-out reconciliation across approved matches and counts of unknown batting/bowling detail.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain.stats import reconciliation


def workspace_integrity(conn: Connection, workspace_id: UUID, *, sample: int = 50) -> dict[str, Any]:
    approved = conn.execute(
        text("SELECT id FROM match WHERE workspace_id = :w AND approval_status IN ('approved','verified_partial') "
             "AND include_in_statistics = true"),
        {"w": workspace_id},
    ).scalars().all()

    reconcile_issues: list[dict[str, Any]] = []
    insufficient = 0
    for mid in approved:
        rep = reconciliation.reconcile_match(conn, workspace_id, mid)
        for inn in rep["innings"]:
            if inn["status"] == "mismatch":
                reconcile_issues.append({"match_id": str(mid), "status": "mismatch",
                                         "recorded": inn["recorded_wickets"],
                                         "from_dismissals": inn["wickets_from_dismissals"]})
            elif inn["status"] == "insufficient":
                insufficient += 1

    def _n(sql: str) -> int:
        return conn.execute(text(sql), {"w": workspace_id}).scalar_one()

    unknown_balls_batting = _n(
        "SELECT count(*) FROM match_stat_contribution WHERE workspace_id = :w AND calculator = 'player_batting' "
        "AND (metrics->>'balls_known')::int < (metrics->>'innings')::int")
    unknown_balls_bowling = _n(
        "SELECT count(*) FROM match_stat_contribution WHERE workspace_id = :w AND calculator = 'player_bowling' "
        "AND (metrics->>'balls_known')::int < (metrics->>'innings')::int")
    unknown_results = _n(
        "SELECT count(*) FROM match WHERE workspace_id = :w AND approval_status IN ('approved','verified_partial') "
        "AND (result_type IS NULL OR result_type = 'unknown')")
    disputed = _n("SELECT count(*) FROM match WHERE workspace_id = :w AND approval_status = 'disputed'")

    return {
        "approved_matches": len(approved),
        "reconciliation_mismatches": len(reconcile_issues),
        "reconciliation_insufficient": insufficient,
        "mismatch_sample": reconcile_issues[:sample],
        "contributions_with_unknown_batting_balls": unknown_balls_batting,
        "contributions_with_unknown_bowling_balls": unknown_balls_bowling,
        "approved_matches_with_unknown_result": unknown_results,
        "disputed_matches": disputed,
        "ok": not reconcile_issues,
        "note": "Approved statistics may rest on incomplete data. Unknown values are preserved (never "
                "zero); affected aggregates are reported as known-minimums, not confirmed totals.",
    }
