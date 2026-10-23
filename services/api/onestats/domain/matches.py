"""Matches & fixtures (Phase 6, Stage 1).

The canonical match header and its two sides. Classification is explicit and independently
editable — the manually entered ``round`` is stored verbatim and is **never** used to decide
whether a match is a final/grand final; a match starts ``unclassified`` and only an administrator
(or a later verified source) sets a category/finals_stage and marks it verified. Results use an
explicit vocabulary with nullable margins; raw source values are preserved and unresolved ones
stay unresolved. ``include_in_statistics`` is owned by OneStats. Match-scope playing conditions
resolve through match → grade → season → competition.

No scorecard body yet (later stages) and no statistics compute (Phase 7). Workspace-scoped (RLS);
governed by ``match.manage``; every mutation audited.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit, playing_conditions

CLASSIFICATIONS = ("home_away", "final", "grand_final", "other", "unclassified")
FINALS_STAGES = ("qualifying_final", "elimination_final", "semi_final", "preliminary_final", "grand_final", "custom")
RESULT_TYPES = ("home_win", "away_win", "tie", "draw", "no_result", "abandoned", "washout", "forfeit", "unknown")
DATE_PRECISIONS = ("unknown", "exact", "year", "month", "approx")
STATUSES = ("draft", "final", "abandoned")

_COLS = (
    "id, workspace_id, competition_id, grade_id, season_id, venue_id, match_date, date_precision, "
    "round, matchtype, format, status, classification, finals_stage, classification_verified, "
    "classification_ref_id, result_type, result_raw, won_by_team_id, margin_runs, margin_wickets, "
    "include_in_statistics, notes, source_system, source_ref, created_at, updated_at"
)


def get_match(conn: Connection, match_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text(f"SELECT {_COLS} FROM match WHERE id = :id"), {"id": match_id}).mappings().first()
    return dict(r) if r else None


def list_match_teams(conn: Connection, match_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("SELECT id, team_id, is_home, captain_person_id, wicketkeeper_person_id, bonus_points "
             "FROM match_team WHERE match_id = :m ORDER BY is_home DESC"),
        {"m": match_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def detail(conn: Connection, match_id: UUID) -> dict[str, Any] | None:
    m = get_match(conn, match_id)
    if m is None:
        return None
    m["teams"] = list_match_teams(conn, match_id)
    return m


def list_matches(
    conn: Connection, *, competition_id: UUID | None = None, grade_id: UUID | None = None,
    season_id: UUID | None = None, venue_id: UUID | None = None, classification: str | None = None,
    status: str | None = None, date_from: Any | None = None, date_to: Any | None = None,
) -> list[dict[str, Any]]:
    # include the home/away team ids (from match_team) so a list view can show both sides without
    # a per-row detail fetch; nullable when a side is not yet recorded.
    sql = (
        f"SELECT {_COLS}, "
        "(SELECT team_id FROM match_team mt WHERE mt.match_id = match.id AND mt.is_home) AS home_team_id, "
        "(SELECT team_id FROM match_team mt WHERE mt.match_id = match.id AND NOT mt.is_home) AS away_team_id "
        "FROM match"
    )
    clauses: list[str] = []
    params: dict[str, Any] = {}
    for col, val in (("competition_id", competition_id), ("grade_id", grade_id),
                     ("season_id", season_id), ("venue_id", venue_id),
                     ("classification", classification), ("status", status)):
        if val is not None:
            clauses.append(f"{col} = :{col}")
            params[col] = val
    if date_from is not None:
        clauses.append("match_date >= :df")
        params["df"] = date_from
    if date_to is not None:
        clauses.append("match_date <= :dt")
        params["dt"] = date_to
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY match_date NULLS FIRST, created_at"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def create_match(
    conn: Connection, workspace_id: UUID, actor: str, *,
    competition_id: UUID | None = None, grade_id: UUID | None = None, season_id: UUID | None = None,
    venue_id: UUID | None = None, match_date: Any | None = None, date_precision: str = "exact",
    round: str | None = None, matchtype: str | None = None, format: str | None = None,
    status: str = "draft", notes: str | None = None,
    source_system: str | None = None, source_ref: str | None = None,
) -> UUID:
    if date_precision not in DATE_PRECISIONS:
        raise ValueError("invalid_date_precision")
    if status not in STATUSES:
        raise ValueError("invalid_status")
    for col, val, table in (("competition_id", competition_id, "competition"),
                            ("grade_id", grade_id, "grade"), ("season_id", season_id, "season"),
                            ("venue_id", venue_id, "venue")):
        if val is not None and conn.execute(text(f"SELECT 1 FROM {table} WHERE id = :x"), {"x": val}).first() is None:
            raise ValueError(f"{table}_not_found")
    match_id = conn.execute(
        text(
            "INSERT INTO match(workspace_id, competition_id, grade_id, season_id, venue_id, match_date, "
            " date_precision, round, matchtype, format, status, notes, source_system, source_ref) "
            "VALUES (:w, :c, :g, :s, :v, :d, :dp, :round, :mt, :fmt, :st, :notes, :ss, :sr) RETURNING id"
        ),
        {"w": workspace_id, "c": competition_id, "g": grade_id, "s": season_id, "v": venue_id,
         "d": match_date, "dp": date_precision, "round": round, "mt": matchtype, "fmt": format,
         "st": status, "notes": notes, "ss": source_system, "sr": source_ref},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "match.create", entity="match", entity_id=str(match_id),
                      after={"round": round, "classification": "unclassified", "status": status})
    return match_id


def update_match(
    conn: Connection, workspace_id: UUID, actor: str, match_id: UUID, **fields: Any,
) -> dict[str, Any]:
    before = get_match(conn, match_id)
    if before is None:
        raise ValueError("match_not_found")
    allowed = {"competition_id", "grade_id", "season_id", "venue_id", "match_date", "date_precision",
               "round", "matchtype", "format", "status", "notes", "include_in_statistics"}
    if "date_precision" in fields and fields["date_precision"] not in DATE_PRECISIONS:
        raise ValueError("invalid_date_precision")
    if "status" in fields and fields["status"] not in STATUSES:
        raise ValueError("invalid_status")
    data = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if data:
        sets = ", ".join(f"{k} = :{k}" for k in data)
        conn.execute(text(f"UPDATE match SET {sets}, updated_at = now() WHERE id = :id"), {**data, "id": match_id})
    after = get_match(conn, match_id)
    audit.write_audit(conn, workspace_id, actor, "match.update", entity="match", entity_id=str(match_id),
                      before=before, after=after)
    return after


def set_classification(
    conn: Connection, workspace_id: UUID, actor: str, match_id: UUID, *, classification: str,
    finals_stage: str | None = None, verified: bool = False, classification_ref_id: UUID | None = None,
) -> dict[str, Any]:
    """Set the explicit match classification. The round label plays no part in this — it is the
    administrator's decision (or a verified source)."""
    before = get_match(conn, match_id)
    if before is None:
        raise ValueError("match_not_found")
    if classification not in CLASSIFICATIONS:
        raise ValueError("invalid_classification")
    if finals_stage is not None and finals_stage not in FINALS_STAGES:
        raise ValueError("invalid_finals_stage")
    conn.execute(
        text("UPDATE match SET classification = :c, finals_stage = :fs, classification_verified = :v, "
             "classification_ref_id = :ref, updated_at = now() WHERE id = :id"),
        {"c": classification, "fs": finals_stage, "v": verified, "ref": classification_ref_id, "id": match_id},
    )
    after = get_match(conn, match_id)
    audit.write_audit(conn, workspace_id, actor, "match.classify", entity="match", entity_id=str(match_id),
                      before=before, after=after)
    return after


def set_result(
    conn: Connection, workspace_id: UUID, actor: str, match_id: UUID, *, result_type: str,
    won_by_team_id: UUID | None = None, margin_runs: int | None = None, margin_wickets: int | None = None,
    result_raw: str | None = None,
) -> dict[str, Any]:
    before = get_match(conn, match_id)
    if before is None:
        raise ValueError("match_not_found")
    if result_type not in RESULT_TYPES:
        raise ValueError("invalid_result_type")
    if won_by_team_id is not None and conn.execute(
        text("SELECT 1 FROM match_team WHERE match_id = :m AND team_id = :t"),
        {"m": match_id, "t": won_by_team_id},
    ).first() is None:
        raise ValueError("winner_not_in_match")
    conn.execute(
        text("UPDATE match SET result_type = :rt, won_by_team_id = :w, margin_runs = :mr, "
             "margin_wickets = :mw, result_raw = coalesce(:raw, result_raw), updated_at = now() WHERE id = :id"),
        {"rt": result_type, "w": won_by_team_id, "mr": margin_runs, "mw": margin_wickets,
         "raw": result_raw, "id": match_id},
    )
    after = get_match(conn, match_id)
    audit.write_audit(conn, workspace_id, actor, "match.result", entity="match", entity_id=str(match_id),
                      before=before, after=after)
    return after


def set_team(
    conn: Connection, workspace_id: UUID, actor: str, match_id: UUID, *, team_id: UUID, is_home: bool,
    captain_person_id: UUID | None = None, wicketkeeper_person_id: UUID | None = None,
    bonus_points: float | None = None,
) -> dict[str, Any]:
    """Add or update a side of the match (idempotent on match+team). Enforces one home + one away
    via the unique side index."""
    if get_match(conn, match_id) is None:
        raise ValueError("match_not_found")
    if conn.execute(text("SELECT 1 FROM team WHERE id = :t"), {"t": team_id}).first() is None:
        raise ValueError("team_not_found")
    existing = conn.execute(
        text("SELECT id FROM match_team WHERE match_id = :m AND team_id = :t"),
        {"m": match_id, "t": team_id},
    ).scalar_one_or_none()
    if existing is not None:
        conn.execute(
            text("UPDATE match_team SET is_home = :h, captain_person_id = :cap, "
                 "wicketkeeper_person_id = :wk, bonus_points = :bp WHERE id = :id"),
            {"h": is_home, "cap": captain_person_id, "wk": wicketkeeper_person_id, "bp": bonus_points, "id": existing},
        )
        mt_id = existing
    else:
        mt_id = conn.execute(
            text("INSERT INTO match_team(workspace_id, match_id, team_id, is_home, captain_person_id, "
                 "wicketkeeper_person_id, bonus_points) VALUES (:w, :m, :t, :h, :cap, :wk, :bp) RETURNING id"),
            {"w": workspace_id, "m": match_id, "t": team_id, "h": is_home, "cap": captain_person_id,
             "wk": wicketkeeper_person_id, "bp": bonus_points},
        ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "match.set_team", entity="match", entity_id=str(match_id),
                      after={"team_id": str(team_id), "is_home": is_home})
    return {"match_team_id": mt_id}


def effective_conditions(conn: Connection, match_id: UUID) -> dict[str, Any]:
    """Resolve the playing conditions in force for a match (match → grade → season → competition)."""
    m = get_match(conn, match_id)
    if m is None:
        raise ValueError("match_not_found")
    return playing_conditions.resolve_effective(
        conn, competition_id=m["competition_id"], season_id=m["season_id"],
        grade_id=m["grade_id"], match_id=match_id,
    )
