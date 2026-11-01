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
                   grade_id: UUID | None, team_id: UUID | None,
                   organisation_id: UUID | None = None) -> dict[str, Any]:
    return {"workspace_id": workspace_id, "competition_id": competition_id, "season_id": season_id,
            "grade_id": grade_id, "team_id": team_id, "organisation_id": organisation_id}


def career_summary(conn: Connection, workspace_id: UUID, person_id: UUID, *, competition_id: UUID | None = None,
                   season_id: UUID | None = None, grade_id: UUID | None = None,
                   team_id: UUID | None = None, organisation_id: UUID | None = None) -> dict[str, Any]:
    """Career totals in each discipline for the selected scope (merge-aware, confirmed from the engine).

    ``organisation_id`` restricts the figures to one club, so a player who has turned out for more than
    one club can be viewed per club or across their whole career."""
    f = _scope_filters(workspace_id, competition_id, season_id, grade_id, team_id, organisation_id)
    bat = engine.person_batting(conn, f, person_id)
    bowl = engine.person_bowling(conn, f, person_id)
    # The summed ledger keeps neither the not-out status of the highest score nor the runs for the best
    # bowling figures, so derive those two from the raw entries (same scope, merge-aware, unknown excluded).
    highest_not_out, best_bowling = _highest_and_bbi(conn, workspace_id, person_id, f)
    bat["highest_not_out"] = highest_not_out
    bowl["best_bowling"] = best_bowling
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


def _highest_and_bbi(conn: Connection, workspace_id: UUID, person_id: UUID,
                     f: dict[str, Any]) -> tuple[bool, dict[str, Any] | None]:
    """Highest score's not-out status, and best bowling in an innings (wickets then fewest runs), from the
    raw entries — the summed ledger keeps neither. Scoped exactly like the summary (merge-aware, official
    matches only); unknown runs/wickets are excluded, never guessed."""
    ids = _merge_ids(conn, person_id)
    params: dict[str, Any] = {"ids": ids, "w": workspace_id}
    mscope = ""
    if f.get("competition_id"):
        mscope += " AND m.competition_id = :comp"; params["comp"] = f["competition_id"]
    if f.get("season_id"):
        mscope += " AND m.season_id = :season"; params["season"] = f["season_id"]
    if f.get("grade_id"):
        mscope += " AND m.grade_id = :grade"; params["grade"] = f["grade_id"]
    bat_scope, bowl_scope = mscope, mscope
    if f.get("team_id"):
        bat_scope += " AND i.batting_team_id = :team"; bowl_scope += " AND i.bowling_team_id = :team"
        params["team"] = f["team_id"]
    if f.get("organisation_id"):
        bat_scope += " AND i.batting_team_id IN (SELECT id FROM team WHERE organisation_id = :org)"
        bowl_scope += " AND i.bowling_team_id IN (SELECT id FROM team WHERE organisation_id = :org)"
        params["org"] = f["organisation_id"]
    official = "m.workspace_id = :w AND m.include_in_statistics = true AND m.approval_status IN ('approved','verified_partial')"
    hs = conn.execute(text(
        "SELECT be.runs AS hs, bool_or(be.dismissal_type IN ('not_out','retired_not_out')) AS no_ "
        "FROM batting_entry be JOIN innings i ON i.id = be.innings_id JOIN match m ON m.id = i.match_id "
        f"WHERE be.person_id = ANY(CAST(:ids AS uuid[])) AND {official} AND be.runs IS NOT NULL{bat_scope} "
        "GROUP BY be.runs ORDER BY be.runs DESC LIMIT 1"), params).mappings().first()
    bb = conn.execute(text(
        "SELECT bo.wickets AS w, bo.runs_conceded AS r "
        "FROM bowling_entry bo JOIN innings i ON i.id = bo.innings_id JOIN match m ON m.id = i.match_id "
        f"WHERE bo.person_id = ANY(CAST(:ids AS uuid[])) AND {official} AND bo.wickets IS NOT NULL{bowl_scope} "
        "ORDER BY bo.wickets DESC, bo.runs_conceded ASC NULLS LAST LIMIT 1"), params).mappings().first()
    highest_not_out = bool(hs["no_"]) if hs else False
    best_bowling = ({"wickets": int(bb["w"]), "runs": int(bb["r"]) if bb["r"] is not None else None}
                    if bb else None)
    return highest_not_out, best_bowling


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


def season_leaderships(conn: Connection, workspace_id: UUID, person_id: UUID) -> list[dict[str, Any]]:
    """Seasons in which this player was the No.1 (or tied No.1) run scorer or wicket taker — the
    "Leading Run Scorer 2017/18" style honours, surfaced as badges. Most recent season first."""
    ids = {str(person_id)} | set(_merge_ids(conn, person_id))
    out: list[dict[str, Any]] = []
    for s in records.seasonal_leaders(conn, workspace_id):
        rs, wt = s.get("leading_run_scorer"), s.get("leading_wicket_taker")
        if rs and ids & set(rs.get("subject_ids") or []):
            out.append({"title": "Leading Run Scorer", "season": s["label"], "value": rs.get("value")})
        if wt and ids & set(wt.get("subject_ids") or []):
            out.append({"title": "Leading Wicket Taker", "season": s["label"], "value": wt.get("value")})
    out.reverse()   # seasonal_leaders is oldest-first; show most recent season first
    return out


def grand_finals(conn: Connection, workspace_id: UUID, person_id: UUID, *,
                 organisation_id: UUID | None = None) -> dict[str, Any]:
    """Grand-final career record for the player: figures restricted to matches classified as grand
    finals (the engine's ``grand_final`` split), plus each grand final played. ``premierships`` is the
    number of grand finals the player's team won while they featured — a recorded result, never inferred."""
    f = {"workspace_id": workspace_id, "split": "grand_final", "organisation_id": organisation_id}
    bat = engine.person_batting(conn, f, person_id)
    bowl = engine.person_bowling(conn, f, person_id)
    field = engine.person_fielding(conn, f, person_id)
    capt = engine.person_captaincy(conn, f, person_id)
    part = engine.person_participation(conn, f, person_id)
    gf_matches = [m for m in match_history(conn, workspace_id, person_id) if m["classification"] == "grand_final"]
    return {
        "appearances": int(part.get("matches", 0) or 0),
        "premierships": int(part.get("wins", 0) or 0),
        "batting": bat, "bowling": bowl, "fielding": field, "captaincy": capt,
        "matches": gf_matches,
        "has_batting": int(bat.get("innings", 0) or 0) > 0,
        "has_bowling": int(bowl.get("innings", 0) or 0) > 0,
        "has_captaincy": int(capt.get("captained", 0) or 0) > 0,
    }


def career_matches_span(conn: Connection, workspace_id: UUID, person_id: UUID, *,
                        organisation_id: UUID | None = None) -> dict[str, Any]:
    """The player's first and most recent recorded match — date + opposition (the other team's club).
    From approved/stats-eligible matches they featured in; missing dates are excluded. Opposition is the
    match's other team; unknown if it can't be resolved — never invented. ``organisation_id`` restricts
    the span to the matches the player featured in for one club."""
    ids = _merge_ids(conn, person_id)

    def _edge(order: str) -> dict[str, Any] | None:
        r = conn.execute(
            text(
                "SELECT m.match_date, "
                " (SELECT coalesce(nullif(o.short_name,''), o.name) FROM match_team mt "
                "  JOIN team t ON t.id = mt.team_id JOIN organisation o ON o.id = t.organisation_id "
                "  WHERE mt.match_id = m.id AND mt.team_id <> pm.team_id LIMIT 1) AS opposition "
                "FROM (SELECT DISTINCT match_id, team_id FROM match_stat_contribution "
                "      WHERE workspace_id = :w AND subject_id = ANY(CAST(:ids AS uuid[])) "
                "        AND team_id IS NOT NULL "
                "        AND (CAST(:org AS uuid) IS NULL "
                "             OR team_id IN (SELECT id FROM team WHERE organisation_id = CAST(:org AS uuid)))) pm "
                "JOIN match m ON m.id = pm.match_id "
                "WHERE m.match_date IS NOT NULL "
                f"ORDER BY m.match_date {order} LIMIT 1"
            ),
            {"w": workspace_id, "ids": ids, "org": organisation_id},
        ).mappings().first()
        if r is None:
            return None
        return {"date": r["match_date"].isoformat() if r["match_date"] else None, "opposition": r["opposition"]}

    return {"first": _edge("ASC"), "last": _edge("DESC")}


def _group_service(rows: list[dict[str, Any]], label_of) -> list[dict[str, Any]]:
    """Group leadership/recognition rows by their label (role / recognition), collecting the seasons each
    was held — for a 'Service & Honours' display like 'Secretary 2021-22, 2022-23'. Order preserved."""
    groups: dict[str, list[str]] = {}
    order: list[str] = []
    for r in rows:
        label = label_of(r)
        if not label:
            continue
        if label not in groups:
            groups[label] = []
            order.append(label)
        season = r.get("season_label")
        if season and season not in groups[label]:
            groups[label].append(season)
    return [{"label": k, "seasons": groups[k]} for k in order]


def full_profile(conn: Connection, workspace_id: UUID, person_id: UUID, *, competition_id: UUID | None = None,
                 season_id: UUID | None = None, organisation_id: UUID | None = None) -> dict[str, Any]:
    """Everything the profile needs in one call (career scope optional), composed from the engines.

    ``organisation_id`` scopes the career figures, grand-final record and match span to one club; the
    ``clubs`` list is always the player's full set of clubs so the caller can offer the choice."""
    det = conn.execute(
        text("SELECT batting_style, bowling_style, is_wicketkeeper, biography FROM person_profile WHERE person_id = :p"),
        {"p": person_id}).mappings().first()
    from onestats.domain import profiles  # player numbers / leadership / recognition
    nums = profiles.list_numbers(conn, person_id)
    lead = profiles.list_leadership(conn, person_id)
    recog = profiles.list_recognition(conn, person_id)
    return {
        "person_id": str(person_id),
        "detail": {"batting_style": (det or {}).get("batting_style"),
                   "bowling_style": (det or {}).get("bowling_style"),
                   "biography": (det or {}).get("biography"),
                   "is_wicketkeeper": bool((det or {}).get("is_wicketkeeper")),
                   "numbers": sorted({str(n["number"]) for n in nums if n.get("number")}),
                   "leadership": _group_service(lead, lambda r: r.get("role")),
                   "recognition": _group_service(recog, lambda r: r.get("title") or r.get("recognition_type"))},
        "span": career_matches_span(conn, workspace_id, person_id, organisation_id=organisation_id),
        "career": career_summary(conn, workspace_id, person_id, competition_id=competition_id,
                                 season_id=season_id, organisation_id=organisation_id),
        "seasons": season_breakdown(conn, workspace_id, person_id),
        "clubs": clubs_and_teams(conn, workspace_id, person_id),
        "records": records_held(conn, workspace_id, person_id),
        "season_leaderships": season_leaderships(conn, workspace_id, person_id),
        "grand_finals": grand_finals(conn, workspace_id, person_id, organisation_id=organisation_id),
        "milestones": milestones.person_milestones(conn, workspace_id, person_id),
        "badges": badges.person_badges(conn, workspace_id, person_id),
        "honours": [{k: (str(v) if isinstance(v, UUID) else v) for k, v in h.items()}
                    for h in honours.list_honours(conn, workspace_id, person_id=person_id)],
    }
