"""Professional player profile aggregation (Phase 13 — player profiles).

Composes the ONE person identity (Phase 5), the Phase 12 statistics engine, the Phase 13 records engine
and honours, and Phase 11 media into a complete career picture: career totals (merge-aware), season-by-
season, match-by-match, records held, milestones, badges, awards/honours and clubs represented. No
statistics are recalculated here and no second identity is created — it only reads and arranges. Career
scope (whole workspace, or a competition/club/season) is explicit; scopes are never silently combined.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain.records import badges, honours, milestones, records
from onestats.domain.stats import engine


def _scope_filters(workspace_id: UUID, competition_id: UUID | None, season_id: UUID | None,
                   grade_id: UUID | None, team_id: UUID | None) -> dict[str, Any]:
    return {"workspace_id": workspace_id, "competition_id": competition_id, "season_id": season_id,
            "grade_id": grade_id, "team_id": team_id}


def career_summary(conn: Connection, workspace_id: UUID, person_id: UUID, *, competition_id: UUID | None = None,
                   season_id: UUID | None = None, grade_id: UUID | None = None,
                   team_id: UUID | None = None) -> dict[str, Any]:
    """Career totals in each discipline for the selected scope (merge-aware, confirmed from the engine)."""
    f = _scope_filters(workspace_id, competition_id, season_id, grade_id, team_id)
    bat = engine.person_batting(conn, f, person_id)
    bowl = engine.person_bowling(conn, f, person_id)
    field = engine.person_fielding(conn, f, person_id)
    capt = engine.person_captaincy(conn, f, person_id)
    part = engine.person_participation(conn, f, person_id)
    # a derived (not invented) primary-role hint from recorded figures only
    runs = int(bat.get("runs", 0) or 0)
    wkts = int(bowl.get("wickets", 0) or 0)
    keeper = int(field.get("keeper_dismissals", 0) or 0)
    if keeper >= 5 and keeper >= wkts:
        role = "wicketkeeper"
    elif runs > 0 and wkts >= 15:
        role = "all-rounder"
    elif wkts > runs // 10 and wkts > 0:
        role = "bowler"
    elif runs > 0:
        role = "batter"
    else:
        role = None
    return {"scope": {k: (str(v) if isinstance(v, UUID) else v) for k, v in f.items()},
            "matches": int(part.get("matches", 0) or 0), "batting": bat, "bowling": bowl,
            "fielding": field, "captaincy": capt, "participation": part, "derived_role": role,
            "has_batting": int(bat.get("innings", 0) or 0) > 0, "has_bowling": int(bowl.get("innings", 0) or 0) > 0,
            "has_captaincy": int(capt.get("captained", 0) or 0) > 0,
            "has_keeping": int(field.get("keeper_dismissals", 0) or 0) > 0}


def _merge_ids(conn: Connection, person_id: UUID) -> list[str]:
    rows = conn.execute(
        text("SELECT id FROM person WHERE id = :p OR merged_into_id = :p"), {"p": person_id}
    ).scalars().all()
    return [str(r) for r in rows]


def season_breakdown(conn: Connection, workspace_id: UUID, person_id: UUID) -> list[dict[str, Any]]:
    """Per-season career line. Seasons the player appeared in, each with that season's figures (not
    combined across seasons; a player in two grades in one season is aggregated for the season line)."""
    ids = _merge_ids(conn, person_id)
    seasons = conn.execute(
        text("SELECT DISTINCT s.id, s.label, s.start_date FROM season s JOIN match_stat_contribution c "
             "ON c.season_id = s.id WHERE c.workspace_id = :w AND c.subject_id = ANY(CAST(:ids AS uuid[])) "
             "ORDER BY s.start_date NULLS LAST, s.label"),
        {"w": workspace_id, "ids": ids},
    ).mappings().all()
    out = []
    for s in seasons:
        f = {"workspace_id": workspace_id, "season_id": s["id"]}
        bat = engine.person_batting(conn, f, person_id)
        bowl = engine.person_bowling(conn, f, person_id)
        field = engine.person_fielding(conn, f, person_id)
        part = engine.person_participation(conn, f, person_id)
        capt = engine.person_captaincy(conn, f, person_id)
        out.append({"season_id": str(s["id"]), "label": s["label"], "matches": int(part.get("matches", 0) or 0),
                    "runs": bat.get("runs", 0), "batting_average": bat.get("average"),
                    "wickets": bowl.get("wickets", 0), "bowling_average": bowl.get("average"),
                    "catches": field.get("catches", 0), "run_outs": field.get("run_outs", 0),
                    "stumpings": field.get("stumpings", 0), "captained": capt.get("captained", 0)})
    return out


def match_history(conn: Connection, workspace_id: UUID, person_id: UUID, *, limit: int = 500) -> list[dict[str, Any]]:
    """Match-by-match career: each match the player featured in, with their batting/bowling/fielding line,
    captaincy flag, opposition/venue/result. Missing figures are left null (not shown as zero)."""
    ids = _merge_ids(conn, person_id)
    rows = conn.execute(
        text(
            "SELECT m.id, m.match_date, m.classification, m.result_type, m.competition_id, "
            "  (SELECT metrics FROM match_stat_contribution x WHERE x.match_id = m.id AND x.calculator='player_batting' "
            "     AND x.subject_id = ANY(CAST(:ids AS uuid[])) LIMIT 1) AS bat, "
            "  (SELECT metrics FROM match_stat_contribution x WHERE x.match_id = m.id AND x.calculator='player_bowling' "
            "     AND x.subject_id = ANY(CAST(:ids AS uuid[])) LIMIT 1) AS bowl, "
            "  (SELECT metrics FROM match_stat_contribution x WHERE x.match_id = m.id AND x.calculator='player_fielding' "
            "     AND x.subject_id = ANY(CAST(:ids AS uuid[])) LIMIT 1) AS field, "
            "  EXISTS (SELECT 1 FROM match_stat_contribution x WHERE x.match_id = m.id AND x.calculator='player_captaincy' "
            "     AND x.subject_id = ANY(CAST(:ids AS uuid[]))) AS captained "
            "FROM match m WHERE m.workspace_id = :w AND m.id IN ("
            "   SELECT DISTINCT match_id FROM match_stat_contribution WHERE workspace_id = :w "
            "     AND subject_id = ANY(CAST(:ids AS uuid[]))) "
            "ORDER BY m.match_date DESC NULLS LAST LIMIT :lim"
        ),
        {"w": workspace_id, "ids": ids, "lim": limit},
    ).mappings().all()
    out = []
    for r in rows:
        bat = r["bat"] or {}
        bowl = r["bowl"] or {}
        field = r["field"] or {}
        out.append({
            "match_id": str(r["id"]), "match_date": r["match_date"].isoformat() if r["match_date"] else None,
            "classification": r["classification"], "result_type": r["result_type"],
            "competition_id": str(r["competition_id"]) if r["competition_id"] else None,
            "runs": bat.get("runs"), "balls": bat.get("balls"), "out": bool(bat.get("dismissed")) if bat else None,
            "wickets": bowl.get("wickets"), "runs_conceded": bowl.get("runs"),
            "catches": field.get("catches"), "stumpings": field.get("stumpings"), "run_outs": field.get("run_outs"),
            "captained": bool(r["captained"]),
        })
    return out


def clubs_and_teams(conn: Connection, workspace_id: UUID, person_id: UUID) -> list[dict[str, Any]]:
    ids = _merge_ids(conn, person_id)
    rows = conn.execute(
        text("SELECT DISTINCT t.id AS team_id, t.name AS team, o.id AS org_id, o.name AS club "
             "FROM match_stat_contribution c JOIN team t ON t.id = c.team_id "
             "JOIN organisation o ON o.id = t.organisation_id "
             "WHERE c.workspace_id = :w AND c.subject_id = ANY(CAST(:ids AS uuid[])) AND c.team_id IS NOT NULL "
             "ORDER BY o.name, t.name"),
        {"w": workspace_id, "ids": ids},
    ).mappings().all()
    return [{"team_id": str(r["team_id"]), "team": r["team"], "org_id": str(r["org_id"]), "club": r["club"]}
            for r in rows]


def records_held(conn: Connection, workspace_id: UUID, person_id: UUID) -> list[dict[str, Any]]:
    """All-time records this player currently holds (No.1, or tied No.1)."""
    pid = str(person_id)
    allr = records.all_time_records(conn, workspace_id, {"workspace_id": workspace_id})
    held = []
    for data in allr.values():
        holder = data.get("holder")
        if not holder:
            continue
        ids = {holder.get("subject_id")} | {t.get("subject_id") for t in (data.get("ties") or [])}
        if pid in ids:
            held.append({"title": data["title"], "value": data.get("value"),
                         "tied": bool(holder.get("tied")), "known_minimum": bool(holder.get("known_minimum"))})
    return held


def full_profile(conn: Connection, workspace_id: UUID, person_id: UUID, *, competition_id: UUID | None = None,
                 season_id: UUID | None = None) -> dict[str, Any]:
    """Everything the profile needs in one call (career scope optional), composed from the engines."""
    return {
        "person_id": str(person_id),
        "career": career_summary(conn, workspace_id, person_id, competition_id=competition_id, season_id=season_id),
        "seasons": season_breakdown(conn, workspace_id, person_id),
        "clubs": clubs_and_teams(conn, workspace_id, person_id),
        "records": records_held(conn, workspace_id, person_id),
        "milestones": milestones.person_milestones(conn, workspace_id, person_id),
        "badges": badges.person_badges(conn, workspace_id, person_id),
        "honours": [{k: (str(v) if isinstance(v, UUID) else v) for k, v in h.items()}
                    for h in honours.list_honours(conn, workspace_id, person_id=person_id)],
    }
