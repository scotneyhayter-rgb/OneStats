"""Finals Series foundation (Phase 4, Stage 6 — revised).

A Finals Series groups the ordered games of a multi-match final (best-of-three/five/custom) or a
single-match final, kept distinct from the individual matches and from a multi-day/multi-innings
single match. A Grand Final *series* (``is_grand_final_series``) is distinguishable from the
individual Grand Final *matches* it contains. Games reference matches by ``match_id`` (resolved in
Phase 8 once the canonical match table exists) and/or ``match_source_ref`` so imported historical
matches can be linked later without destructive change.

This module provides the series/team/game structure and outcome. **Match-level statistics and
appearance/premiership counting depend on the canonical match model and are deferred to Phase 8**
(documented, not implemented here). All operations are workspace-scoped (RLS), governed by
``competition.manage``, and audited.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

FORMATS = ("single", "best_of_3", "best_of_5", "custom")
OUTCOMES = ("in_progress", "decided", "drawn", "tied", "incomplete", "abandoned", "unresolved")

_COLS = (
    "id, workspace_id, competition_id, season_id, grade_id, name, format, is_grand_final_series, "
    "outcome, winner_team_id, outcome_notes, rules, evidence, source_system, source_ref, created_at"
)


def get_series(conn: Connection, series_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(
        text(f"SELECT {_COLS} FROM finals_series WHERE id = :id"), {"id": series_id}
    ).mappings().first()
    return dict(r) if r else None


def list_series(conn: Connection, *, competition_id: UUID | None = None) -> list[dict[str, Any]]:
    sql = f"SELECT {_COLS} FROM finals_series"
    params: dict[str, Any] = {}
    if competition_id is not None:
        sql += " WHERE competition_id = :c"
        params["c"] = competition_id
    sql += " ORDER BY created_at"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def create_series(
    conn: Connection, workspace_id: UUID, actor: str, *, competition_id: UUID, name: str,
    format: str = "single", season_id: UUID | None = None, grade_id: UUID | None = None,
    is_grand_final_series: bool = False, rules: dict[str, Any] | None = None,
    evidence: str | None = None, source_system: str | None = None, source_ref: str | None = None,
) -> UUID:
    name = (name or "").strip()
    if not name:
        raise ValueError("missing_name")
    if format not in FORMATS:
        raise ValueError("invalid_format")
    if conn.execute(text("SELECT 1 FROM competition WHERE id = :c"), {"c": competition_id}).first() is None:
        raise ValueError("competition_not_found")
    series_id = conn.execute(
        text(
            "INSERT INTO finals_series"
            "(workspace_id, competition_id, season_id, grade_id, name, format, is_grand_final_series, "
            " rules, evidence, source_system, source_ref) "
            "VALUES (:w, :c, :s, :g, :n, :f, :gf, CAST(:rules AS jsonb), :ev, :ss, :sr) RETURNING id"
        ),
        {"w": workspace_id, "c": competition_id, "s": season_id, "g": grade_id, "n": name,
         "f": format, "gf": is_grand_final_series,
         "rules": json.dumps(rules) if rules is not None else None,
         "ev": evidence, "ss": source_system, "sr": source_ref},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "finals_series.create", entity="finals_series",
                      entity_id=str(series_id),
                      after={"name": name, "format": format, "is_grand_final_series": is_grand_final_series})
    return series_id


def add_team(
    conn: Connection, workspace_id: UUID, actor: str, series_id: UUID, team_id: UUID,
    *, seed_label: str | None = None,
) -> dict[str, Any]:
    if get_series(conn, series_id) is None:
        raise ValueError("series_not_found")
    if conn.execute(text("SELECT 1 FROM team WHERE id = :t"), {"t": team_id}).first() is None:
        raise ValueError("team_not_found")
    existing = conn.execute(
        text("SELECT id FROM finals_series_team WHERE series_id = :s AND team_id = :t"),
        {"s": series_id, "t": team_id},
    ).scalar_one_or_none()
    if existing is not None:
        return {"series_team_id": existing, "created": False}
    sid = conn.execute(
        text(
            "INSERT INTO finals_series_team(workspace_id, series_id, team_id, seed_label) "
            "VALUES (:w, :s, :t, :seed) RETURNING id"
        ),
        {"w": workspace_id, "s": series_id, "t": team_id, "seed": seed_label},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "finals_series.add_team", entity="finals_series",
                      entity_id=str(series_id), after={"team_id": str(team_id)})
    return {"series_team_id": sid, "created": True}


def list_teams(conn: Connection, series_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("SELECT id, team_id, seed_label FROM finals_series_team WHERE series_id = :s ORDER BY created_at"),
        {"s": series_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def add_game(
    conn: Connection, workspace_id: UUID, actor: str, series_id: UUID, *, game_number: int,
    match_id: UUID | None = None, match_source_ref: str | None = None, notes: str | None = None,
) -> dict[str, Any]:
    """Add an ordered game to the series. A multi-day/multi-innings match is ONE game — never split
    into several. ``match_id`` links a canonical match (Phase 8); ``match_source_ref`` links an
    imported historical match now, to be resolved later without destructive change. Idempotent on
    (series, game_number)."""
    if get_series(conn, series_id) is None:
        raise ValueError("series_not_found")
    if game_number < 1:
        raise ValueError("invalid_game_number")
    existing = conn.execute(
        text("SELECT id FROM finals_series_game WHERE series_id = :s AND game_number = :g"),
        {"s": series_id, "g": game_number},
    ).scalar_one_or_none()
    if existing is not None:
        conn.execute(
            text(
                "UPDATE finals_series_game SET match_id = coalesce(:mid, match_id), "
                "match_source_ref = coalesce(:sr, match_source_ref), notes = coalesce(:n, notes) WHERE id = :id"
            ),
            {"mid": match_id, "sr": match_source_ref, "n": notes, "id": existing},
        )
        return {"game_id": existing, "created": False}
    gid = conn.execute(
        text(
            "INSERT INTO finals_series_game(workspace_id, series_id, game_number, match_id, match_source_ref, notes) "
            "VALUES (:w, :s, :g, :mid, :sr, :n) RETURNING id"
        ),
        {"w": workspace_id, "s": series_id, "g": game_number, "mid": match_id, "sr": match_source_ref, "n": notes},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "finals_series.add_game", entity="finals_series",
                      entity_id=str(series_id),
                      after={"game_number": game_number, "match_source_ref": match_source_ref})
    return {"game_id": gid, "created": True}


def list_games(conn: Connection, series_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT id, game_number, match_id, match_source_ref, notes FROM finals_series_game "
            "WHERE series_id = :s ORDER BY game_number"
        ),
        {"s": series_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def set_outcome(
    conn: Connection, workspace_id: UUID, actor: str, series_id: UUID, *, outcome: str,
    winner_team_id: UUID | None = None, outcome_notes: str | None = None,
) -> dict[str, Any]:
    before = get_series(conn, series_id)
    if before is None:
        raise ValueError("series_not_found")
    if outcome not in OUTCOMES:
        raise ValueError("invalid_outcome")
    if winner_team_id is not None:
        is_participant = conn.execute(
            text("SELECT 1 FROM finals_series_team WHERE series_id = :s AND team_id = :t"),
            {"s": series_id, "t": winner_team_id},
        ).first() is not None
        if not is_participant:
            raise ValueError("winner_not_participant")
    conn.execute(
        text(
            "UPDATE finals_series SET outcome = :o, winner_team_id = :w, "
            "outcome_notes = coalesce(:n, outcome_notes) WHERE id = :id"
        ),
        {"o": outcome, "w": winner_team_id, "n": outcome_notes, "id": series_id},
    )
    after = get_series(conn, series_id)
    audit.write_audit(conn, workspace_id, actor, "finals_series.set_outcome", entity="finals_series",
                      entity_id=str(series_id), before=before, after=after)
    return after


def detail(conn: Connection, series_id: UUID) -> dict[str, Any] | None:
    s = get_series(conn, series_id)
    if s is None:
        return None
    s["teams"] = list_teams(conn, series_id)
    s["games"] = list_games(conn, series_id)
    return s
