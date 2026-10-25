"""Competition points & ladders (Phase 12, Stage 12.12).

Computes standings using the competition's **configured** points scheme (the ``points`` JSONB resolved
per competition/season/grade/match by playing conditions — never modern defaults imposed on historical
competitions). Each match result maps to a scheme points value; recorded bonus points / penalties
(``match_team.bonus_points``, net) are added. Only approved, statistics-eligible matches count; results
are the recorded results (provenance preserved); unknown results are excluded, not assumed.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import playing_conditions

# A transparent, documented default when a competition has no configured scheme (editable per workspace).
DEFAULT_SCHEME = {"win": 4, "tie": 2, "draw": 2, "no_result": 1, "abandoned": 1, "washout": 1, "loss": 0}


def _result_key(result_type: str | None, team_id: Any, won_by: Any) -> str | None:
    if result_type in ("home_win", "away_win", "forfeit"):
        if won_by is None:
            return None  # unknown winner — excluded
        return "win" if str(team_id) == str(won_by) else "loss"
    if result_type in ("tie", "draw", "no_result", "abandoned", "washout"):
        return result_type
    return None  # unknown / unrecorded — excluded (never assumed)


def ladder(conn: Connection, workspace_id: UUID, *, competition_id: UUID, season_id: UUID | None = None,
           grade_id: UUID | None = None) -> dict[str, Any]:
    scheme = (playing_conditions.resolve_effective(
        conn, competition_id=competition_id, season_id=season_id, grade_id=grade_id
    )["conditions"].get("points")) or DEFAULT_SCHEME

    sql = (
        "SELECT mt.team_id, mt.bonus_points, m.result_type, m.won_by_team_id, m.first_innings_winner_team_id "
        "FROM match_team mt JOIN match m ON m.id = mt.match_id "
        "WHERE m.workspace_id = :w AND m.competition_id = :c "
        "AND m.approval_status IN ('approved','verified_partial') AND m.include_in_statistics = true"
    )
    params: dict[str, Any] = {"w": workspace_id, "c": competition_id}
    if season_id:
        sql += " AND m.season_id = :s"
        params["s"] = season_id
    if grade_id:
        sql += " AND m.grade_id = :g"
        params["g"] = grade_id
    rows = conn.execute(text(sql), params).mappings().all()

    table: dict[str, dict[str, Any]] = {}
    for r in rows:
        key = _result_key(r["result_type"], r["team_id"], r["won_by_team_id"])
        t = table.setdefault(str(r["team_id"]), {
            "team_id": str(r["team_id"]), "played": 0, "wins": 0, "losses": 0, "draws": 0, "ties": 0,
            "no_results": 0, "unknown": 0, "bonus": 0.0, "first_innings": 0.0, "points": 0.0})
        t["played"] += 1
        if r["bonus_points"] is not None:
            t["bonus"] += float(r["bonus_points"])
            t["points"] += float(r["bonus_points"])
        # multi-day: first-innings result points (configurable; NULL winner skips this)
        fiw = r["first_innings_winner_team_id"]
        if fiw is not None:
            fi_key = "first_innings_win" if str(r["team_id"]) == str(fiw) else "first_innings_loss"
            fi_pts = float(scheme.get(fi_key, 0))
            t["first_innings"] += fi_pts
            t["points"] += fi_pts
        if key is None:
            t["unknown"] += 1
            continue
        t["points"] += float(scheme.get(key, 0))
        if key == "win":
            t["wins"] += 1
        elif key == "loss":
            t["losses"] += 1
        elif key == "draw":
            t["draws"] += 1
        elif key == "tie":
            t["ties"] += 1
        else:
            t["no_results"] += 1

    standings = sorted(table.values(), key=lambda t: (-t["points"], -t["wins"], t["losses"]))
    for i, t in enumerate(standings, 1):
        t["position"] = i
        t["points"] = round(t["points"], 2)
        t["bonus"] = round(t["bonus"], 2)
        t["first_innings"] = round(t["first_innings"], 2)
    return {"competition_id": str(competition_id), "scheme": scheme, "standings": standings,
            "note": "Points use the competition's configured scheme; unknown results are excluded, not "
                    "assumed. Historical competitions keep their own scheme."}
