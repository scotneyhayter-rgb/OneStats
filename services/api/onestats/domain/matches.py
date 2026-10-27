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
DATE_PRECISIONS = ("unknown", "exact", "year", "month", "approx", "range", "season")
STATUSES = ("draft", "final", "abandoned")

TOSS_DECISIONS = ("bat", "field", "no_toss", "not_recorded", "unknown")

_COLS = (
    "id, workspace_id, competition_id, grade_id, season_id, season_source, venue_id, match_date, match_date_end, date_precision, "
    "round, matchtype, format, status, classification, finals_stage, classification_verified, "
    "classification_ref_id, result_type, result_raw, result_source, result_override_reason, "
    "won_by_team_id, first_innings_winner_team_id, margin_runs, margin_wickets, "
    "toss_winner_team_id, toss_decision, "
    "include_in_statistics, approval_status, approval_reason, approved_by, approved_at, "
    "revised_since_approval, notes, source_system, source_ref, created_at, updated_at"
)

APPROVAL_STATUSES = ("draft", "awaiting_approval", "approved", "rejected", "verified_partial", "disputed")
# Verified states whose present data is authoritative for official statistics (Phase 7 'approved' plus
# Phase 10 'verified_partial' — a known-incomplete but reviewer-verified record). 'disputed' is NOT here.
VERIFIED_STATUSES = ("approved", "verified_partial")


def get_match(conn: Connection, match_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text(f"SELECT {_COLS} FROM match WHERE id = :id"), {"id": match_id}).mappings().first()
    return dict(r) if r else None


def list_match_teams(conn: Connection, match_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("SELECT id, team_id, is_home, captain_person_id, acting_captain_person_id, "
             "wicketkeeper_person_id, wicketkeeper2_person_id, bonus_points "
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
    sql += " ORDER BY match_date DESC NULLS LAST, created_at DESC"
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
    allowed = {"competition_id", "grade_id", "season_id", "venue_id", "match_date", "match_date_end",
               "date_precision", "round", "matchtype", "format", "status", "notes", "include_in_statistics"}
    if "date_precision" in fields and fields["date_precision"] not in DATE_PRECISIONS:
        raise ValueError("invalid_date_precision")
    if "status" in fields and fields["status"] not in STATUSES:
        raise ValueError("invalid_status")
    data = {k: v for k, v in fields.items() if k in allowed and v is not None}
    # a season set explicitly here is a manual choice — mark it so auto-assignment never overwrites it
    if "season_id" in data:
        data["season_source"] = "manual"
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


RESULT_SOURCES = ("calculated", "recorded", "manual", "unknown")


def set_result(
    conn: Connection, workspace_id: UUID, actor: str, match_id: UUID, *, result_type: str,
    won_by_team_id: UUID | None = None, margin_runs: int | None = None, margin_wickets: int | None = None,
    result_raw: str | None = None, result_source: str = "recorded", result_override_reason: str | None = None,
    first_innings_winner_team_id: UUID | None = None,
) -> dict[str, Any]:
    before = get_match(conn, match_id)
    if before is None:
        raise ValueError("match_not_found")
    if result_type not in RESULT_TYPES:
        raise ValueError("invalid_result_type")
    if result_source not in RESULT_SOURCES:
        raise ValueError("invalid_result_source")
    if won_by_team_id is not None and conn.execute(
        text("SELECT 1 FROM match_team WHERE match_id = :m AND team_id = :t"),
        {"m": match_id, "t": won_by_team_id},
    ).first() is None:
        raise ValueError("winner_not_in_match")
    if first_innings_winner_team_id is not None and conn.execute(
        text("SELECT 1 FROM match_team WHERE match_id = :m AND team_id = :t"),
        {"m": match_id, "t": first_innings_winner_team_id},
    ).first() is None:
        raise ValueError("first_innings_winner_not_in_match")
    conn.execute(
        text("UPDATE match SET result_type = :rt, won_by_team_id = :w, margin_runs = :mr, "
             "margin_wickets = :mw, result_raw = coalesce(:raw, result_raw), result_source = :rs, "
             "result_override_reason = :reason, "
             "first_innings_winner_team_id = coalesce(:fiw, first_innings_winner_team_id), "
             "updated_at = now() WHERE id = :id"),
        {"rt": result_type, "w": won_by_team_id, "mr": margin_runs, "mw": margin_wickets,
         "raw": result_raw, "rs": result_source, "reason": result_override_reason,
         "fiw": first_innings_winner_team_id, "id": match_id},
    )
    after = get_match(conn, match_id)
    audit.write_audit(conn, workspace_id, actor, "match.result", entity="match", entity_id=str(match_id),
                      before=before, after=after)
    return after


def set_approval(
    conn: Connection, workspace_id: UUID, actor: str, match_id: UUID, *,
    status: str, reason: str | None = None,
) -> dict[str, Any]:
    """Set the scorecard approval status (draft/awaiting_approval/approved/rejected) — independent of
    the match's cricket status. Records who approved and when (only while 'approved'); audited. Only
    an 'approved' scorecard is authoritative for official statistics (Stage 7.8 enforces that)."""
    before = get_match(conn, match_id)
    if before is None:
        raise ValueError("match_not_found")
    if status not in APPROVAL_STATUSES:
        raise ValueError("invalid_approval_status")
    verified = status in VERIFIED_STATUSES
    # a verified decision (approved / verified_partial) clears the revision flag and records the reviewer
    conn.execute(
        text("UPDATE match SET approval_status = :s, approval_reason = :r, "
             "approved_by = :by, approved_at = :at, "
             "revised_since_approval = (revised_since_approval AND NOT :verified), updated_at = now() "
             "WHERE id = :id"),
        {"s": status, "r": reason, "by": actor if verified else None,
         "at": None, "verified": verified, "id": match_id},
    )
    if verified:
        conn.execute(text("UPDATE match SET approved_at = now() WHERE id = :id"), {"id": match_id})
    after = get_match(conn, match_id)
    audit.write_audit(conn, workspace_id, actor, "match.approval", entity="match", entity_id=str(match_id),
                      before=before, after=after)
    # update the official-statistics ledger (Stage 7.8): approving writes the match's contributions,
    # any other status removes them. Editing an approved scorecard does NOT run this, so the ledger
    # keeps the last approved version until re-approval.
    from onestats.domain import recalc  # local import avoids a module cycle
    recalc.recompute_match(conn, workspace_id, actor, match_id)
    return after


def mark_revised_if_approved(conn: Connection, match_id: UUID) -> None:
    """Flag that an APPROVED scorecard has changed since approval, so official statistics keep using
    the last approved version until the revision is re-approved. No-op unless currently approved."""
    conn.execute(
        text("UPDATE match SET revised_since_approval = true, updated_at = now() "
             "WHERE id = :id AND approval_status = 'approved'"),
        {"id": match_id},
    )


def official_for_stats(match: dict[str, Any]) -> bool:
    """Whether a match's data may contribute to OFFICIAL statistics: it must be in a verified state
    (approved, or Phase 10 verified_partial) and flagged for statistical inclusion. A verified_partial
    record only ever contributes the data it actually has — nothing is inferred to fill gaps. 'disputed',
    'draft', 'awaiting_approval' and 'rejected' never contribute. Used by the recalc framework (7.8)."""
    return match.get("approval_status") in VERIFIED_STATUSES and bool(match.get("include_in_statistics"))


def set_toss(
    conn: Connection, workspace_id: UUID, actor: str, match_id: UUID, *,
    toss_winner_team_id: UUID | None = None, toss_decision: str | None = None,
) -> dict[str, Any]:
    """Record the toss. The winner (if given) must be a side of the match; the decision is taken
    from a controlled vocabulary (``bat``/``field``/``no_toss``/``not_recorded``/``unknown``). The
    toss is never inferred from the batting order — both values are explicit."""
    before = get_match(conn, match_id)
    if before is None:
        raise ValueError("match_not_found")
    if toss_decision is not None and toss_decision not in TOSS_DECISIONS:
        raise ValueError("invalid_toss_decision")
    if toss_winner_team_id is not None and conn.execute(
        text("SELECT 1 FROM match_team WHERE match_id = :m AND team_id = :t"),
        {"m": match_id, "t": toss_winner_team_id},
    ).first() is None:
        raise ValueError("toss_winner_not_in_match")
    conn.execute(
        text("UPDATE match SET toss_winner_team_id = :w, toss_decision = :d, updated_at = now() WHERE id = :id"),
        {"w": toss_winner_team_id, "d": toss_decision, "id": match_id},
    )
    after = get_match(conn, match_id)
    audit.write_audit(conn, workspace_id, actor, "match.toss", entity="match", entity_id=str(match_id),
                      before=before, after=after)
    return after


def set_team(
    conn: Connection, workspace_id: UUID, actor: str, match_id: UUID, *, team_id: UUID, is_home: bool,
    captain_person_id: UUID | None = None, wicketkeeper_person_id: UUID | None = None,
    acting_captain_person_id: UUID | None = None, wicketkeeper2_person_id: UUID | None = None,
    bonus_points: float | None = None,
) -> dict[str, Any]:
    """Add or update a side of the match (idempotent on match+team). Enforces one home + one away
    via the unique side index. Captain / acting captain / keeper / second keeper are match-specific
    and set explicitly (a null value clears that role); historically accurate, never inferred."""
    if get_match(conn, match_id) is None:
        raise ValueError("match_not_found")
    if conn.execute(text("SELECT 1 FROM team WHERE id = :t"), {"t": team_id}).first() is None:
        raise ValueError("team_not_found")
    existing = conn.execute(
        text("SELECT id FROM match_team WHERE match_id = :m AND team_id = :t"),
        {"m": match_id, "t": team_id},
    ).scalar_one_or_none()
    params = {"h": is_home, "cap": captain_person_id, "acap": acting_captain_person_id,
              "wk": wicketkeeper_person_id, "wk2": wicketkeeper2_person_id, "bp": bonus_points}
    if existing is not None:
        conn.execute(
            text("UPDATE match_team SET is_home = :h, captain_person_id = :cap, "
                 "acting_captain_person_id = :acap, wicketkeeper_person_id = :wk, "
                 "wicketkeeper2_person_id = :wk2, bonus_points = :bp WHERE id = :id"),
            {**params, "id": existing},
        )
        mt_id = existing
    else:
        mt_id = conn.execute(
            text("INSERT INTO match_team(workspace_id, match_id, team_id, is_home, captain_person_id, "
                 "acting_captain_person_id, wicketkeeper_person_id, wicketkeeper2_person_id, bonus_points) "
                 "VALUES (:w, :m, :t, :h, :cap, :acap, :wk, :wk2, :bp) RETURNING id"),
            {"w": workspace_id, "m": match_id, "t": team_id, **params},
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
