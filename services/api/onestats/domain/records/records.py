"""All-time record holders & seasonal leaders (Phase 13, Stages 13.1-13.4, 13.9-13.11).

Composes the Phase 12 engine leaderboards — never reimplements a formula. Each record exposes the No. 1
holder prominently, an expanded ranking, and ties (genuine ties are preserved, not broken arbitrarily).
Known-minimum values are flagged so a record is not presented as a confirmed exact total without
qualification.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain.stats import engine, partnerships

# (key, title, calculator-leaderboard, value metric, order_by)
_SPECS: list[tuple[str, str, str, str, str]] = [
    ("most_runs", "Most Career Runs", "batting", "runs", "runs"),
    ("highest_score", "Highest Individual Score", "batting", "highest_score", "highest_score"),
    ("most_centuries", "Most Centuries", "batting", "hundreds", "hundreds"),
    ("most_fifties", "Most Half-Centuries", "batting", "fifties", "fifties"),
    ("most_wickets", "Most Career Wickets", "bowling", "wickets", "wickets"),
    ("best_match_bowling", "Best Bowling in a Match", "bowling", "best_match_wickets", "best_match_wickets"),
    ("most_five_fors", "Most Five-Wicket Innings", "bowling", "five_wkt_innings", "five_wkt_innings"),
    ("most_matches", "Most Matches Played", "participation", "matches", "matches"),
    ("most_catches", "Most Catches", "fielding", "catches", "catches"),
    ("most_stumpings", "Most Stumpings", "fielding", "stumpings", "stumpings"),
    ("most_run_outs", "Most Run Outs", "fielding", "run_outs", "run_outs"),
    ("most_captained", "Most Matches Captained", "captaincy", "captained", "captained"),
    ("most_captain_wins", "Most Wins as Captain", "captaincy", "wins", "wins"),
]

_LEADERS = {
    "batting": lambda conn, f, ob: engine.batting_leaders(conn, f, order_by=ob),
    "bowling": lambda conn, f, ob: engine.bowling_leaders(conn, f, order_by=ob),
    "fielding": lambda conn, f, ob: engine.fielding_leaders(conn, f, order_by=ob),
    "captaincy": lambda conn, f, ob: engine.captaincy_leaders(conn, f, order_by=ob, min_eligible=0),
    "participation": lambda conn, f, ob: engine.participation_leaders(conn, f, order_by=ob),
}


def _names(conn: Connection, workspace_id: UUID) -> dict[str, str]:
    return {str(r["id"]): r["display_name"] for r in conn.execute(
        text("SELECT id, display_name FROM person WHERE workspace_id = :w"), {"w": workspace_id}).mappings()}


def clubs_for(conn: Connection, workspace_id: UUID, filters: dict[str, Any],
              mode: str = "primary") -> dict[str, str]:
    """Map each player to the club(s) they represented, derived from their appearances (the team they
    batted or bowled for) in approved, statistics-eligible matches within the same scope as the records.
    ``mode='primary'`` → the single club with the most appearances; ``mode='global'`` → every club
    represented (comma-separated). Never invented — a player with no club-resolvable appearance is omitted."""
    base = (
        "SELECT ap.person_id AS pid, coalesce(nullif(o.short_name,''), o.name) AS club, "
        " count(DISTINCT ap.match_id) AS apps "
        "FROM (SELECT be.person_id, i.batting_team_id AS team_id, i.match_id "
        "      FROM batting_entry be JOIN innings i ON i.id = be.innings_id "
        "      UNION SELECT bo.person_id, i.bowling_team_id, i.match_id "
        "      FROM bowling_entry bo JOIN innings i ON i.id = bo.innings_id) ap "
        "JOIN match m ON m.id = ap.match_id "
        "JOIN team t ON t.id = ap.team_id JOIN organisation o ON o.id = t.organisation_id "
        "WHERE m.workspace_id = :w AND m.approval_status IN ('approved','verified_partial') "
        "AND m.include_in_statistics = true AND ap.person_id IS NOT NULL AND ap.team_id IS NOT NULL"
    )
    params: dict[str, Any] = {"w": workspace_id}
    for key, col in (("season_id", "m.season_id"), ("grade_id", "m.grade_id"),
                     ("competition_id", "m.competition_id")):
        if filters.get(key):
            base += f" AND {col} = :{key}"
            params[key] = filters[key]
    base += " GROUP BY ap.person_id, club"
    byp: dict[str, list[tuple[str, int]]] = {}
    for r in conn.execute(text(base), params).mappings():
        byp.setdefault(str(r["pid"]), []).append((r["club"], int(r["apps"])))
    out: dict[str, str] = {}
    for pid, lst in byp.items():
        lst.sort(key=lambda x: (-x[1], x[0]))          # most appearances first, then name
        out[pid] = ", ".join(dict.fromkeys(c for c, _ in lst)) if mode == "global" else lst[0][0]
    return out


def all_time_records(conn: Connection, workspace_id: UUID, filters: dict[str, Any], *, top: int = 10,
                     club_mode: str = "primary") -> dict[str, Any]:
    names = _names(conn, workspace_id)
    clubs = clubs_for(conn, workspace_id, filters, club_mode)

    def _club(pid: str) -> str | None:
        return clubs.get(str(pid))
    out: dict[str, Any] = {}
    for key, title, which, metric, order_by in _SPECS:
        rows = _LEADERS[which](conn, filters, order_by)
        rows = [r for r in rows if (r.get(metric) or 0) > 0]
        if not rows:
            out[key] = {"title": title, "metric": metric, "holder": None, "ranking": []}
            continue
        top_val = rows[0].get(metric)
        for r in rows:
            r["player"] = names.get(r["subject_id"], "Unknown")
        ties = [r for r in rows if r.get(metric) == top_val]
        out[key] = {
            "title": title, "metric": metric, "value": top_val,
            "holder": {"player": rows[0]["player"], "subject_id": rows[0]["subject_id"], "value": top_val,
                       "club": _club(rows[0]["subject_id"]),
                       "tied": len(ties) > 1, "known_minimum": bool(rows[0].get("runs_known_minimum")
                                                                     or rows[0].get("wickets_known_minimum"))},
            "ties": [{"player": r["player"], "subject_id": r["subject_id"], "club": _club(r["subject_id"])}
                     for r in ties] if len(ties) > 1 else [],
            "ranking": [{"rank": i + 1, "player": r["player"], "subject_id": r["subject_id"],
                         "club": _club(r["subject_id"]), "value": r.get(metric)} for i, r in enumerate(rows[:top])],
        }
    # highest partnership (from partnership data). batter1/batter2 are person IDs; resolve to names and
    # present the pair together ("A & B") so the record names BOTH batsmen, not just the value.
    bp = partnerships.batting_partnerships(conn, filters, limit=top)

    def _pair(row: dict[str, Any]) -> str:
        return f"{names.get(row['batter1'], 'Unknown')} & {names.get(row['batter2'], 'Unknown')}"

    def _pair_club(row: dict[str, Any]) -> str | None:
        c1, c2 = _club(row["batter1"]), _club(row["batter2"])
        if c1 and c2:
            return c1 if c1 == c2 else f"{c1} / {c2}"
        return c1 or c2

    out["highest_partnership"] = {
        "title": "Highest Partnership", "metric": "runs",
        "value": bp[0]["runs"] if bp else None,
        "holder": ({"player": _pair(bp[0]), "value": bp[0]["runs"], "tied": False, "known_minimum": False,
                    "club": _pair_club(bp[0]),
                    "runs": bp[0]["runs"], "batter1": bp[0]["batter1"], "batter2": bp[0]["batter2"],
                    "batter1_name": names.get(bp[0]["batter1"], "Unknown"),
                    "batter2_name": names.get(bp[0]["batter2"], "Unknown"),
                    "wicket": bp[0]["wicket"], "match_id": bp[0]["match_id"]} if bp else None),
        "ranking": [{"rank": i + 1, "player": _pair(r), "club": _pair_club(r), "value": r["runs"]}
                    for i, r in enumerate(bp)],
    }
    return out


def seasonal_leaders(conn: Connection, workspace_id: UUID, *, competition_id: UUID | None = None) -> list[dict[str, Any]]:
    """Per season: the No. 1 run scorer and wicket taker (ties preserved). Seasons are not combined."""
    names = _names(conn, workspace_id)
    sql = ("SELECT DISTINCT s.id, s.label, s.start_date FROM season s "
           "JOIN match m ON m.season_id = s.id AND m.workspace_id = s.workspace_id "
           "WHERE s.workspace_id = :w AND m.approval_status IN ('approved','verified_partial')")
    params: dict[str, Any] = {"w": workspace_id}
    if competition_id:
        sql += " AND m.competition_id = :c"
        params["c"] = competition_id
    sql += " ORDER BY s.start_date NULLS LAST, s.label"
    seasons = conn.execute(text(sql), params).mappings().all()

    out = []
    for s in seasons:
        f = {"workspace_id": workspace_id, "season_id": s["id"]}
        bat = [r for r in engine.batting_leaders(conn, f, order_by="runs", limit=5) if r["runs"] > 0]
        bowl = [r for r in engine.bowling_leaders(conn, f, order_by="wickets", limit=5) if r["wickets"] > 0]

        def _lead(rows: list[dict[str, Any]], metric: str) -> dict[str, Any] | None:
            if not rows:
                return None
            top_val = rows[0][metric]
            tied = [names.get(r["subject_id"], "Unknown") for r in rows if r[metric] == top_val]
            return {"player": tied[0], "value": top_val, "tied": tied if len(tied) > 1 else []}

        out.append({"season_id": str(s["id"]), "label": s["label"],
                    "leading_run_scorer": _lead(bat, "runs"), "leading_wicket_taker": _lead(bowl, "wickets")})
    return out
