"""Read-only match scorecard assembly — a traditional batting + bowling card built from the stored
innings, batting and bowling entries, for viewing / printing / sharing a completed match.

Nothing is invented and unknown is never shown as zero: a missing figure stays blank. The dismissal text
is composed in standard notation (``c Fielder b Bowler``, ``lbw b Bowler``, ``run out``, ``not out`` …)
from the recorded dismissal type and the credited bowler/fielder.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import batting, bowling, matches
from onestats.domain import innings as inn

# Dismissal statuses that are NOT a batter being out (for the innings wicket tally / "out" flag).
_NOT_OUT = (None, "not_out", "retired_not_out", "dnb", "absent", "retired", "unknown")
_DID_NOT_BAT = ("dnb", "absent")


def _person_names(conn: Connection, match_id: UUID) -> dict[str, str]:
    rows = conn.execute(
        text(
            "SELECT id, display_name FROM person WHERE id IN ("
            " SELECT person_id FROM batting_entry be JOIN innings i ON i.id = be.innings_id"
            "   WHERE i.match_id = :m AND person_id IS NOT NULL"
            " UNION SELECT bowler_person_id FROM batting_entry be JOIN innings i ON i.id = be.innings_id"
            "   WHERE i.match_id = :m AND bowler_person_id IS NOT NULL"
            " UNION SELECT fielder_person_id FROM batting_entry be JOIN innings i ON i.id = be.innings_id"
            "   WHERE i.match_id = :m AND fielder_person_id IS NOT NULL"
            " UNION SELECT person_id FROM bowling_entry bo JOIN innings i ON i.id = bo.innings_id"
            "   WHERE i.match_id = :m AND person_id IS NOT NULL)"
        ),
        {"m": match_id},
    ).mappings().all()
    return {str(r["id"]): r["display_name"] for r in rows}


def _team_names(conn: Connection, match_id: UUID) -> dict[str, str]:
    rows = conn.execute(
        text(
            "SELECT id, name FROM team WHERE id IN ("
            " SELECT team_id FROM match_team WHERE match_id = :m"
            " UNION SELECT batting_team_id FROM innings WHERE match_id = :m AND batting_team_id IS NOT NULL"
            " UNION SELECT bowling_team_id FROM innings WHERE match_id = :m AND bowling_team_id IS NOT NULL)"
        ),
        {"m": match_id},
    ).mappings().all()
    return {str(r["id"]): r["name"] for r in rows}


def _how_out(r: dict[str, Any], names: dict[str, str]) -> str:
    """Standard dismissal notation from the recorded type + credited bowler/fielder. A missing bowler or
    fielder shows as '?' rather than being invented."""
    dt = r.get("dismissal_type")
    b = names.get(str(r.get("bowler_person_id"))) if r.get("bowler_person_id") else None
    f = names.get(str(r.get("fielder_person_id"))) if r.get("fielder_person_id") else None
    bowler, fielder = b or "?", f or "?"
    simple = {
        "not_out": "not out", "retired_not_out": "retired not out", "retired": "retired",
        "retired_out": "retired out", "dnb": "did not bat", "absent": "absent",
        "obstructing": "obstructing the field", "hit_twice": "hit the ball twice",
        "timed_out": "timed out", "unknown_out": "out", "unknown": "", None: "",
    }
    if dt in simple:
        return simple[dt]
    if dt == "bowled":
        return f"b {bowler}"
    if dt == "lbw":
        return f"lbw b {bowler}"
    if dt in ("caught", "caught_behind"):
        return f"c {fielder} b {bowler}"
    if dt == "caught_and_bowled":
        return f"c & b {bowler}"
    if dt == "stumped":
        return f"st {fielder} b {bowler}"
    if dt == "hit_wicket":
        return f"hit wkt b {bowler}"
    if dt == "run_out":
        return f"run out ({f})" if f else "run out"
    return str(dt).replace("_", " ")


def _home_away(conn: Connection, match_id: UUID) -> tuple[str | None, str | None]:
    rows = conn.execute(
        text("SELECT team_id, is_home FROM match_team WHERE match_id = :m"), {"m": match_id}
    ).mappings().all()
    home = next((str(r["team_id"]) for r in rows if r["is_home"]), None)
    away = next((str(r["team_id"]) for r in rows if r["is_home"] is False), None)
    return home, away


def _result_text(m: dict[str, Any], teams: dict[str, str]) -> str | None:
    """Mirrors the app's result line: a named label for non-wins, else the winner and the margin."""
    t = m.get("result_type")
    if not t or t == "unknown":
        return None
    labels = {"tie": "Match tied", "draw": "Match drawn", "no_result": "No result",
              "abandoned": "Match abandoned", "washout": "Washed out", "forfeit": "Match forfeited"}
    if t in labels:
        return labels[t]
    won = teams.get(str(m.get("won_by_team_id"))) if m.get("won_by_team_id") else None
    won = won or "Winner"
    if m.get("margin_runs") is not None:
        n = int(m["margin_runs"])
        return f"{won} won by {n} run{'' if n == 1 else 's'}"
    if m.get("margin_wickets") is not None:
        n = int(m["margin_wickets"])
        return f"{won} won by {n} wicket{'' if n == 1 else 's'}"
    return f"{won} won"


def scorecard_view(conn: Connection, workspace_id: UUID, match_id: UUID) -> dict[str, Any]:
    """Assemble the full read-only scorecard: a header (teams, date, venue, result, toss) and, per innings,
    the batting card (with standard dismissal notation), the extras and total, and the bowling card."""
    m = matches.get_match(conn, match_id) or {}
    names = _person_names(conn, match_id)
    teams = _team_names(conn, match_id)
    out_innings: list[dict[str, Any]] = []
    for iv in inn.list_innings(conn, match_id):
        bats = batting.list_entries(conn, iv["id"])
        bowls = bowling.list_entries(conn, iv["id"])
        batting_rows = []
        for b in bats:
            runs, balls = b.get("runs"), b.get("balls_faced")
            batting_rows.append({
                "name": names.get(str(b.get("person_id")), "Unknown") if b.get("person_id") else "Unknown",
                "how_out": _how_out(b, names),
                "runs": runs, "balls": balls, "fours": b.get("fours"), "sixes": b.get("sixes"),
                "strike_rate": round(runs / balls * 100, 1) if runs is not None and balls else None,
                "out": b.get("dismissal_type") not in _NOT_OUT,
                "did_not_bat": b.get("dismissal_type") in _DID_NOT_BAT,
            })
        bowling_rows = []
        for w in bowls:
            rc, lb = w.get("runs_conceded"), w.get("legal_balls")
            bowling_rows.append({
                "name": names.get(str(w.get("person_id")), "Unknown") if w.get("person_id") else "Unknown",
                "overs": w.get("overs_text"), "maidens": w.get("maidens"), "runs": rc,
                "wickets": w.get("wickets"), "wides": w.get("wides"), "noballs": w.get("noballs"),
                "economy": round(rc / (lb / 6), 2) if rc is not None and lb else None,
            })
        extras = {k: iv.get(k) for k in ("byes", "legbyes", "wides", "noballs", "penalty")}
        extras_total = sum(int(v or 0) for v in extras.values())
        bat_runs = sum(int(b["runs"] or 0) for b in bats if b.get("runs") is not None)
        official = iv.get("official_total")
        out_innings.append({
            "inns_number": iv.get("inns_number"),
            "batting_team": teams.get(str(iv.get("batting_team_id")), "Batting team"),
            "bowling_team": teams.get(str(iv.get("bowling_team_id")), ""),
            "status": iv.get("status"), "declared": iv.get("status") == "declared",
            "batting": batting_rows, "bowling": bowling_rows,
            "extras": extras, "extras_total": extras_total,
            "total": official if official is not None else bat_runs + extras_total,
            "official_total": official, "wickets": iv.get("official_wickets"),
        })
    home_id, away_id = _home_away(conn, match_id)
    home = teams.get(home_id) if home_id else None
    away = teams.get(away_id) if away_id else None
    toss_team = teams.get(str(m.get("toss_winner_team_id"))) if m.get("toss_winner_team_id") else None
    toss = (f"{toss_team} won the toss and chose to {m.get('toss_decision')}"
            if toss_team and m.get("toss_decision") else None)
    return {
        "match_id": str(match_id),
        "home_team": home, "away_team": away,
        "match_date": m.get("match_date").isoformat() if m.get("match_date") else None,
        "format": m.get("format"), "result": _result_text(m, teams), "toss": toss,
        "innings": out_innings,
    }
