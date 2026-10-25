"""Run-out reconciliation (Phase 12, Stage 12.5).

Run outs contribute to the innings wickets lost but are never credited as bowler wickets. This module
reconciles each innings' recorded wickets against its dismissals, surfaces a visible Run Outs count for
the bowling summary, and preserves dismissal provenance. Where the scorecard is incomplete it reports a
warning rather than inventing a dismissal; retired-hurt (retired_not_out / retired) never counts as a
wicket.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain.batting import BOWLER_CREDIT

# Non-bowler dismissals that still count as a wicket in the innings fall.
_OTHER_WICKET = ("retired_out", "obstructing", "hit_twice", "timed_out", "unknown_out")
# Not wickets (no fall): did-not-bat, not out, retired hurt / unresolved retirement, unknown.
_NON_WICKET = ("dnb", "absent", "not_out", "retired_not_out", "retired", "unknown")


def reconcile_innings(conn: Connection, innings_id: UUID) -> dict[str, Any]:
    inn = conn.execute(
        text("SELECT id, official_wickets FROM innings WHERE id = :i"), {"i": innings_id}
    ).mappings().first()
    if inn is None:
        raise ValueError("innings_not_found")
    rows = conn.execute(
        text("SELECT dismissal_type AS dt, count(*) AS n FROM batting_entry WHERE innings_id = :i "
             "GROUP BY dismissal_type"),
        {"i": innings_id},
    ).mappings().all()
    counts = {r["dt"]: int(r["n"]) for r in rows}
    bowler = sum(n for dt, n in counts.items() if dt in BOWLER_CREDIT)
    run_outs = counts.get("run_out", 0)
    other = sum(n for dt, n in counts.items() if dt in _OTHER_WICKET)
    unresolved = sum(n for dt, n in counts.items() if dt in ("retired", "unknown"))
    wickets_from_dismissals = bowler + run_outs + other
    recorded = inn["official_wickets"]

    warnings: list[str] = []
    if recorded is None:
        status = "insufficient"
        warnings.append("Innings wickets not recorded — reconciliation not possible without inventing a dismissal.")
    elif recorded == wickets_from_dismissals:
        status = "reconciled"
    else:
        status = "mismatch"
        warnings.append(
            f"Recorded wickets ({recorded}) do not match the {wickets_from_dismissals} dismissals on the "
            "scorecard; some dismissals may be missing or miscoded (not auto-corrected).")
    if unresolved:
        warnings.append(f"{unresolved} dismissal(s) are unresolved (retired/unknown) and are not counted as wickets.")

    return {
        "innings_id": str(innings_id),
        "recorded_wickets": recorded,
        "bowler_credited": bowler,
        "run_outs": run_outs,
        "other_non_bowler_wickets": other,
        "wickets_from_dismissals": wickets_from_dismissals,
        "unresolved": unresolved,
        "status": status,
        "warnings": warnings,
    }


def reconcile_match(conn: Connection, workspace_id: UUID, match_id: UUID) -> dict[str, Any]:
    innings = conn.execute(
        text("SELECT id FROM innings WHERE match_id = :m AND workspace_id = :w ORDER BY inns_number"),
        {"m": match_id, "w": workspace_id},
    ).scalars().all()
    reports = [reconcile_innings(conn, i) for i in innings]
    return {
        "match_id": str(match_id),
        "innings": reports,
        "ok": all(r["status"] == "reconciled" for r in reports) if reports else None,
        "total_run_outs": sum(r["run_outs"] for r in reports),
    }
