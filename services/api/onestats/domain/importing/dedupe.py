"""Confidence-based duplicate match detection (Phase 8, Stage 8.5 — STEP 7).

Identifies whether an incoming match already exists, distinguishing an **exact** match (same source
identifier, or every available field agreeing) from a **possible** one (a partial agreement). It
never merges anything: it returns ranked candidates with reasons so an administrator decides. Teams
are compared by canonical id, which is already alias-aware (historical names resolve to one team).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

EXACT_THRESHOLD = 0.95


def find_match_duplicates(
    conn: Connection, workspace_id: UUID, *, source_system: str, source_ref: str | None,
    match_date: Any, home_team_id: UUID | None, away_team_id: UUID | None,
    grade_id: UUID | None = None, venue_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Ranked existing matches that may be this one. Each: {match_id, confidence, kind, reasons}."""
    results: dict[str, dict[str, Any]] = {}

    def _add(mid: str, confidence: float, kind: str, reason: str) -> None:
        cur = results.get(mid)
        if cur is None or confidence > cur["confidence"]:
            results[mid] = {"match_id": mid, "confidence": round(confidence, 3), "kind": kind,
                            "reasons": (cur["reasons"] + [reason]) if cur else [reason]}
        elif cur is not None:
            cur["reasons"].append(reason)

    # 1) exact by source identifier — the same source already promoted this match
    if source_ref:
        row = conn.execute(
            text("SELECT id FROM match WHERE source_system = :ss AND source_ref = :sr"),
            {"ss": source_system, "sr": source_ref},
        ).scalar_one_or_none()
        if row is not None:
            _add(str(row), 1.0, "exact", "same source identifier")

    # 2) by fixture — same date with BOTH teams present (orientation-independent). Needs date + teams.
    if match_date and home_team_id and away_team_id:
        rows = conn.execute(
            text("SELECT m.id, m.grade_id, m.venue_id FROM match m "
                 "WHERE m.match_date = :d "
                 "AND EXISTS (SELECT 1 FROM match_team mt WHERE mt.match_id = m.id AND mt.team_id = :home) "
                 "AND EXISTS (SELECT 1 FROM match_team mt WHERE mt.match_id = m.id AND mt.team_id = :away)"),
            {"d": match_date, "home": home_team_id, "away": away_team_id},
        ).mappings().all()
        for r in rows:
            confidence = 0.7
            reasons = ["same date and both teams"]
            if grade_id is not None and r["grade_id"] == grade_id:
                confidence += 0.15
                reasons.append("same grade")
            if venue_id is not None and r["venue_id"] == venue_id:
                confidence += 0.15
                reasons.append("same venue")
            kind = "exact" if confidence >= EXACT_THRESHOLD else "possible"
            for reason in reasons:
                _add(str(r["id"]), confidence, kind, reason)

    return sorted(results.values(), key=lambda x: x["confidence"], reverse=True)
