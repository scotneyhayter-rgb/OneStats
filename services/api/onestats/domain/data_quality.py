"""Data-quality checks — scorer-error "linting" over a workspace's scorecards (audit Deliverable D, P3).

CricketStatz ships ~20 data-quality reports that catch scorer mistakes (a missing fielder, a bowler
also listed as the fielder, a captain/keeper not recorded, a batter entered twice, …). This is the
OneStats equivalent: a set of deterministic checks, each returning the offending matches with enough
detail to open and fix them. It NEVER auto-corrects and NEVER invents data — it only surfaces what a
human should review. Complements ``stats.integrity`` (which reconciles approved figures and counts
unknown detail); this module is about correctness of the entered scorecard, regardless of approval.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

# A check: (key, title, description, severity, SQL returning match_id, match_date, detail).
# Dismissal-type groups are inlined as safe literals (fixed enum values, never user input).
_CHECKS: list[tuple[str, str, str, str, str]] = [
    ("missing_fielder", "Fielder missing on a dismissal that needs one",
     "A run-out, catch or stumping with no fielder recorded — the fielding credit is lost until it is set.",
     "warning",
     ("SELECT m.id AS match_id, m.match_date, be.dismissal_type AS detail "
      "FROM batting_entry be JOIN innings i ON i.id = be.innings_id JOIN match m ON m.id = i.match_id "
      "WHERE m.workspace_id = :w AND be.fielder_person_id IS NULL "
      "AND be.dismissal_type IN ('run_out','caught','caught_behind','stumped')")),
    ("missing_bowler", "Bowler missing on a bowler-credited dismissal",
     "A bowled/lbw/caught/stumped dismissal with no bowler recorded — the wicket can't be credited.",
     "warning",
     ("SELECT m.id AS match_id, m.match_date, be.dismissal_type AS detail "
      "FROM batting_entry be JOIN innings i ON i.id = be.innings_id JOIN match m ON m.id = i.match_id "
      "WHERE m.workspace_id = :w AND be.bowler_person_id IS NULL "
      "AND be.dismissal_type IN ('bowled','lbw','caught','caught_behind','stumped','caught_and_bowled','hit_wicket')")),
    ("bowler_is_fielder", "Bowler also listed as the fielder on a catch",
     "A catch where the same person is both bowler and fielder — this should be recorded as caught & bowled.",
     "warning",
     ("SELECT m.id AS match_id, m.match_date, 'caught: bowler = fielder' AS detail "
      "FROM batting_entry be JOIN innings i ON i.id = be.innings_id JOIN match m ON m.id = i.match_id "
      "WHERE m.workspace_id = :w AND be.dismissal_type = 'caught' "
      "AND be.bowler_person_id IS NOT NULL AND be.bowler_person_id = be.fielder_person_id")),
    ("captain_missing", "Captain not recorded for a side",
     "A match side with no captain recorded — captaincy stats exclude it.",
     "info",
     ("SELECT m.id AS match_id, m.match_date, CASE WHEN mt.is_home THEN 'home side' ELSE 'away side' END AS detail "
      "FROM match_team mt JOIN match m ON m.id = mt.match_id "
      "WHERE m.workspace_id = :w AND mt.captain_person_id IS NULL")),
    ("keeper_missing", "Wicketkeeper not recorded for a side",
     "A match side with no wicketkeeper recorded — keeper dismissals can't be attributed to the keeper.",
     "info",
     ("SELECT m.id AS match_id, m.match_date, CASE WHEN mt.is_home THEN 'home side' ELSE 'away side' END AS detail "
      "FROM match_team mt JOIN match m ON m.id = mt.match_id "
      "WHERE m.workspace_id = :w AND mt.wicketkeeper_person_id IS NULL")),
    ("duplicate_batter", "A batter appears twice in one innings",
     "The same player has more than one batting entry in a single innings — a batter can be dismissed only once.",
     "warning",
     ("SELECT m.id AS match_id, m.match_date, 'player has 2+ batting entries in an innings' AS detail "
      "FROM batting_entry be JOIN innings i ON i.id = be.innings_id JOIN match m ON m.id = i.match_id "
      "WHERE m.workspace_id = :w AND be.person_id IS NOT NULL "
      "GROUP BY m.id, m.match_date, i.id, be.person_id HAVING count(*) > 1")),
    ("duplicate_bowler", "A bowler appears twice in one innings",
     "The same player has more than one bowling entry in a single innings — spells should be combined into one line.",
     "warning",
     ("SELECT m.id AS match_id, m.match_date, 'player has 2+ bowling entries in an innings' AS detail "
      "FROM bowling_entry be JOIN innings i ON i.id = be.innings_id JOIN match m ON m.id = i.match_id "
      "WHERE m.workspace_id = :w AND be.person_id IS NOT NULL "
      "GROUP BY m.id, m.match_date, i.id, be.person_id HAVING count(*) > 1")),
    ("innings_no_batting", "Innings recorded with no batting card",
     "An innings exists but has no batting entries — the scorecard is incomplete.",
     "info",
     ("SELECT m.id AS match_id, m.match_date, 'innings has no batting entries' AS detail "
      "FROM innings i JOIN match m ON m.id = i.match_id "
      "WHERE m.workspace_id = :w AND NOT EXISTS (SELECT 1 FROM batting_entry be WHERE be.innings_id = i.id)")),
]


def scan(conn: Connection, workspace_id: UUID, *, match_id: UUID | None = None,
         sample: int = 100) -> dict[str, Any]:
    """Run every data-quality check over the workspace, or a single match when ``match_id`` is given (so the
    scorecard editor can check the card in front of the scorer). Returns each check with its total issue count
    and a bounded sample of offending matches (id + date + detail) for drill-down. Read-only; nothing changes."""
    checks: list[dict[str, Any]] = []
    total = 0
    params: dict[str, Any] = {"w": workspace_id}
    if match_id is not None:
        params["mid"] = match_id
    for key, title, desc, severity, sql in _CHECKS:
        # every check filters on ``m.workspace_id = :w``; scope to one match by extending that same clause
        q = sql.replace("m.workspace_id = :w", "m.workspace_id = :w AND m.id = :mid") if match_id is not None else sql
        rows = conn.execute(text(q), params).mappings().all()
        total += len(rows)
        checks.append({
            "key": key, "title": title, "description": desc, "severity": severity,
            "count": len(rows),
            "sample": [{"match_id": str(r["match_id"]),
                        "match_date": r["match_date"].isoformat() if r["match_date"] else None,
                        "detail": r["detail"]} for r in rows[:sample]],
        })
    checks.sort(key=lambda c: (-c["count"]))
    return {
        "checks": checks,
        "total_issues": total,
        "ok": total == 0,
        "note": "Scorer-error checks over the entered scorecards. Nothing is auto-corrected; open each "
                "match to review and fix. Historical imports may show expected gaps (e.g. captains/keepers "
                "not recorded in old data) — these are flagged honestly, not treated as errors to hide.",
    }
