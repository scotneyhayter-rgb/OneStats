"""Statistics engine query service (Phase 12, Stage 12.1-12.11).

Aggregates the approved-statistics ledger into leaderboards and per-subject aggregates, with one
consistent set of filters/scopes (season, grade, competition, team, match classification split, home/
away venue, format, date range). Averages/strike rates/economy are computed here from the summed
components; unknown is preserved (e.g. strike rate is over *recorded* balls only, flagged when some
balls faced are unknown). Nothing is fabricated.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

# classification split -> match.classification value (stored in the contribution metrics)
_SPLIT = {"home_away": "home_away", "finals": "final", "grand_final": "grand_final"}


def _needs_match_join(filters: dict[str, Any]) -> bool:
    """A join to ``match`` is only needed for format/date filters — scope, team, split and venue are all
    on the contribution row (or in its metrics). Skipping the join keeps large-dataset queries fast."""
    return bool(filters.get("format") or filters.get("date_from") or filters.get("date_to"))


def _where(filters: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Build the shared WHERE clause + params for a ledger query (alias ``c`` for the contribution,
    ``m`` for the match when joined)."""
    clauses: list[str] = ["c.workspace_id = :w"]
    params: dict[str, Any] = {"w": filters["workspace_id"]}
    for key, col in (("season_id", "c.season_id"), ("grade_id", "c.grade_id"),
                     ("competition_id", "c.competition_id"), ("team_id", "c.team_id")):
        if filters.get(key):
            clauses.append(f"{col} = :{key}")
            params[key] = filters[key]
    split = filters.get("split")
    if split and split in _SPLIT:
        clauses.append("c.metrics->>'classification' = :split_cls")
        params["split_cls"] = _SPLIT[split]
    venue = filters.get("venue")
    if venue == "home":
        clauses.append("c.metrics->>'is_home' = 'true'")
    elif venue == "away":
        clauses.append("c.metrics->>'is_home' = 'false'")
    if filters.get("format"):
        clauses.append("m.format = :format")
        params["format"] = filters["format"]
    if filters.get("date_from"):
        clauses.append("m.match_date >= :date_from")
        params["date_from"] = filters["date_from"]
    if filters.get("date_to"):
        clauses.append("m.match_date <= :date_to")
        params["date_to"] = filters["date_to"]
    return " AND ".join(clauses), params


def _rows(conn: Connection, calculator: str, filters: dict[str, Any], select: str,
          group: str = "c.subject_id", having: str | None = None, order: str | None = None,
          limit: int | None = None) -> list[dict[str, Any]]:
    where, params = _where(filters)
    join = "JOIN match m ON m.id = c.match_id " if _needs_match_join(filters) else ""
    sql = (f"SELECT c.subject_id, {select} FROM match_stat_contribution c "
           f"{join}"
           f"WHERE c.calculator = :cal AND {where} GROUP BY {group}")
    params["cal"] = calculator
    if having:
        sql += f" HAVING {having}"
    if order:
        sql += f" ORDER BY {order}"
    if limit:
        sql += " LIMIT :lim"
        params["lim"] = limit
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def _num(metric: str, as_: str, agg: str = "sum") -> str:
    return f"coalesce({agg}((c.metrics->>'{metric}')::numeric),0) AS {as_}"


# ---- batting ------------------------------------------------------------------------------------
_BAT_SELECT = (
    "count(DISTINCT c.match_id) AS matches, " + _num("innings", "innings") + ", " + _num("runs", "runs")
    + ", " + _num("runs_known", "runs_known")
    + ", " + _num("balls", "balls") + ", " + _num("balls_known", "balls_known") + ", "
    + _num("fours", "fours") + ", " + _num("sixes", "sixes") + ", " + _num("dismissed", "dismissed")
    + ", " + _num("not_out", "not_out") + ", " + _num("fifties", "fifties") + ", "
    + _num("hundreds", "hundreds") + ", " + _num("ducks", "ducks")
    + ", coalesce(max((c.metrics->>'hs')::int),0) AS highest_score"
    + ", coalesce(max((c.metrics->>'match_runs')::int),0) AS most_runs_in_match"
    + ", count(*) AS contributions"
)


def _bat_row(r: dict[str, Any]) -> dict[str, Any]:
    runs, dismissed, balls = int(r["runs"]), int(r["dismissed"]), int(r["balls"])
    innings, balls_known = int(r["innings"]), int(r["balls_known"])
    d = {
        "subject_id": str(r["subject_id"]), "matches": int(r["matches"]), "innings": innings,
        "runs": runs, "not_outs": int(r["not_out"]), "dismissed": dismissed, "balls": balls,
        "fours": int(r["fours"]), "sixes": int(r["sixes"]), "boundaries": int(r["fours"]) + int(r["sixes"]),
        "fifties": int(r["fifties"]),
        "hundreds": int(r["hundreds"]), "ducks": int(r["ducks"]), "highest_score": int(r["highest_score"]),
        "most_runs_in_match": int(r["most_runs_in_match"]),
        "average": round(runs / dismissed, 2) if dismissed else None,
        "strike_rate": round(runs * 100 / balls, 2) if balls else None,
        # strike rate is over recorded balls only; flag when some innings had unknown balls faced
        "balls_incomplete": balls_known < innings,
        # runs are a known-minimum when some innings had unknown runs (never treated as zero)
        "runs_known_minimum": int(r["runs_known"]) < innings,
    }
    return d


def batting_leaders(conn: Connection, filters: dict[str, Any], *, order_by: str = "runs",
                    limit: int = 100, min_runs: int | None = None) -> list[dict[str, Any]]:
    rows = [_bat_row(r) for r in _rows(conn, "player_batting", filters, _BAT_SELECT)]
    if min_runs is not None:
        for r in rows:
            r["qualified"] = r["runs"] >= min_runs
    _sort(rows, order_by)
    return rows[:limit]


# ---- bowling ------------------------------------------------------------------------------------
_BOWL_SELECT = (
    "count(DISTINCT c.match_id) AS matches, " + _num("innings", "innings") + ", " + _num("balls", "balls")
    + ", " + _num("balls_known", "balls_known") + ", " + _num("maidens", "maidens") + ", "
    + _num("runs", "runs") + ", " + _num("wickets", "wickets") + ", " + _num("wickets_known", "wickets_known") + ", "
    + _num("five_wkt_innings", "five_wkt_innings") + ", " + _num("ten_wkt_match", "ten_wkt_match")
    + ", coalesce(max((c.metrics->>'match_wickets')::int),0) AS best_match_wickets"
    + ", count(*) AS contributions"
)


def _bowl_row(r: dict[str, Any], over_length: int = 6) -> dict[str, Any]:
    runs, wickets, balls = int(r["runs"]), int(r["wickets"]), int(r["balls"])
    overs = balls / over_length if over_length else 0
    return {
        "subject_id": str(r["subject_id"]), "matches": int(r["matches"]), "innings": int(r["innings"]),
        "balls": balls, "overs": round(overs, 1), "maidens": int(r["maidens"]), "runs": runs,
        "wickets": wickets, "five_wkt_innings": int(r["five_wkt_innings"]),
        "ten_wkt_match": int(r["ten_wkt_match"]), "best_match_wickets": int(r["best_match_wickets"]),
        "average": round(runs / wickets, 2) if wickets else None,
        "economy": round(runs / overs, 2) if overs else None,
        "strike_rate": round(balls / wickets, 2) if wickets else None,
        "balls_incomplete": int(r["balls_known"]) < int(r["innings"]),
        "wickets_known_minimum": int(r["wickets_known"]) < int(r["innings"]),
    }


def bowling_leaders(conn: Connection, filters: dict[str, Any], *, order_by: str = "wickets",
                    limit: int = 100, over_length: int = 6, min_wickets: int | None = None) -> list[dict[str, Any]]:
    rows = [_bowl_row(r, over_length) for r in _rows(conn, "player_bowling", filters, _BOWL_SELECT)]
    if min_wickets is not None:
        for r in rows:
            r["qualified"] = r["wickets"] >= min_wickets
    _sort(rows, order_by)
    return rows[:limit]


# ---- fielding / wicketkeeping -------------------------------------------------------------------
_FIELD_SELECT = (
    "count(DISTINCT c.match_id) AS matches, " + _num("catches", "catches") + ", "
    + _num("field_catches", "field_catches") + ", " + _num("keeper_catches", "keeper_catches") + ", "
    + _num("stumpings", "stumpings") + ", " + _num("run_outs", "run_outs") + ", "
    + _num("keeper_dismissals", "keeper_dismissals")
)


def fielding_leaders(conn: Connection, filters: dict[str, Any], *, order_by: str = "catches",
                     limit: int = 100) -> list[dict[str, Any]]:
    rows = [{"subject_id": str(r["subject_id"]), "matches": int(r["matches"]),
             "catches": int(r["catches"]), "field_catches": int(r["field_catches"]),
             "keeper_catches": int(r["keeper_catches"]), "stumpings": int(r["stumpings"]),
             "run_outs": int(r["run_outs"]), "keeper_dismissals": int(r["keeper_dismissals"])}
            for r in _rows(conn, "player_fielding", filters, _FIELD_SELECT)]
    _sort(rows, order_by)
    return rows[:limit]


# ---- captaincy ----------------------------------------------------------------------------------
_CAPT_SELECT = (
    _num("captained", "captained") + ", " + _num("win", "wins") + ", " + _num("loss", "losses") + ", "
    + _num("draw", "draws") + ", " + _num("tie", "ties") + ", " + _num("no_result", "no_results") + ", "
    + _num("gf_captained", "gf_captained") + ", " + _num("gf_win", "gf_wins")
)


def captaincy_leaders(conn: Connection, filters: dict[str, Any], *, order_by: str = "captained",
                      limit: int = 100, min_eligible: int = 20) -> list[dict[str, Any]]:
    out = []
    for r in _rows(conn, "player_captaincy", filters, _CAPT_SELECT):
        captained = int(r["captained"])
        wins, draws, ties, no_res = int(r["wins"]), int(r["draws"]), int(r["ties"]), int(r["no_results"])
        eligible = captained - no_res  # eligible excludes no-results/abandoned (unknown excluded upstream)
        out.append({
            "subject_id": str(r["subject_id"]), "captained": captained, "wins": wins,
            "losses": int(r["losses"]), "draws": draws, "ties": ties, "no_results": no_res,
            "gf_captained": int(r["gf_captained"]), "gf_wins": int(r["gf_wins"]), "eligible": eligible,
            "win_pct": round(wins * 100 / eligible, 1) if eligible else None,
            "qualified": eligible >= min_eligible,
        })
    _sort(out, order_by)
    return out[:limit]


# ---- participation / team -----------------------------------------------------------------------
def participation_leaders(conn: Connection, filters: dict[str, Any], *, order_by: str = "matches",
                          limit: int = 100) -> list[dict[str, Any]]:
    sel = "count(DISTINCT c.match_id) AS matches, " + _num("win", "wins") + ", " + _num("loss", "losses")
    rows = [{"subject_id": str(r["subject_id"]), "matches": int(r["matches"]),
             "wins": int(r["wins"]), "losses": int(r["losses"])}
            for r in _rows(conn, "player_appearance", filters, sel)]
    _sort(rows, order_by)
    return rows[:limit]


def team_records(conn: Connection, filters: dict[str, Any], *, order_by: str = "wins",
                 limit: int = 100) -> list[dict[str, Any]]:
    sel = (_num("played", "played") + ", " + _num("win", "wins") + ", " + _num("loss", "losses")
           + ", " + _num("draw", "draws") + ", " + _num("tie", "ties") + ", " + _num("no_result", "no_results"))
    rows = [{"subject_id": str(r["subject_id"]), "played": int(r["played"]), "wins": int(r["wins"]),
             "losses": int(r["losses"]), "draws": int(r["draws"]), "ties": int(r["ties"]),
             "no_results": int(r["no_results"]),
             "win_pct": round(int(r["wins"]) * 100 / (int(r["played"]) - int(r["no_results"])), 1)
             if (int(r["played"]) - int(r["no_results"])) else None}
            for r in _rows(conn, "team_result", filters, sel)]
    _sort(rows, order_by)
    return rows[:limit]


# ---- helpers ------------------------------------------------------------------------------------
def _sort(rows: list[dict[str, Any]], order_by: str) -> None:
    rows.sort(key=lambda r: (r.get(order_by) is None, -(r.get(order_by) or 0)))


def _person_agg(conn: Connection, calculator: str, filters: dict[str, Any], person_id: UUID,
                select: str, row_fn) -> dict[str, Any]:
    """Aggregate one person's figures (merge-aware), via a direct subject filter."""
    where, params = _where(filters)
    params["cal"] = calculator
    params["pid"] = person_id
    join = "JOIN match m ON m.id = c.match_id " if _needs_match_join(filters) else ""
    # aggregate the WHOLE merge-aware set into one row — no GROUP BY, because a merged person's
    # contributions span more than one subject_id and must all be summed together.
    sql = (f"SELECT {select} FROM match_stat_contribution c {join}"
           f"WHERE c.calculator = :cal AND {where} "
           "AND (c.subject_id = :pid OR c.subject_id IN (SELECT id FROM person WHERE merged_into_id = :pid))")
    # With no GROUP BY the aggregate always returns exactly one row (all-zero via coalesce when the
    # person has no contributions), so a missing row only happens on an empty result set. Note: not every
    # calculator selects a ``matches`` column (captaincy does not), so the guard must not depend on it.
    r = conn.execute(text(sql), params).mappings().first()
    if r is None:
        return {"subject_id": str(person_id), "matches": 0, "innings": 0, "runs": 0, "wickets": 0}
    d = dict(r)
    d["subject_id"] = str(person_id)
    return row_fn(d)


def person_batting(conn: Connection, filters: dict[str, Any], person_id: UUID) -> dict[str, Any]:
    return _person_agg(conn, "player_batting", filters, person_id, _BAT_SELECT, _bat_row)


def person_bowling(conn: Connection, filters: dict[str, Any], person_id: UUID, *, over_length: int = 6) -> dict[str, Any]:
    return _person_agg(conn, "player_bowling", filters, person_id, _BOWL_SELECT, lambda r: _bowl_row(r, over_length))


def person_participation(conn: Connection, filters: dict[str, Any], person_id: UUID) -> dict[str, Any]:
    sel = "count(DISTINCT c.match_id) AS matches, " + _num("win", "wins") + ", " + _num("loss", "losses")
    return _person_agg(conn, "player_appearance", filters, person_id, sel,
                       lambda r: {"matches": int(r["matches"]), "wins": int(r["wins"]), "losses": int(r["losses"])})


def person_captaincy(conn: Connection, filters: dict[str, Any], person_id: UUID) -> dict[str, Any]:
    return _person_agg(conn, "player_captaincy", filters, person_id, _CAPT_SELECT,
                       lambda r: {"captained": int(r["captained"]), "wins": int(r["wins"]),
                                  "losses": int(r["losses"]), "draws": int(r["draws"]), "ties": int(r["ties"]),
                                  "no_results": int(r["no_results"]), "gf_captained": int(r["gf_captained"]),
                                  "gf_wins": int(r["gf_wins"])})


def person_fielding(conn: Connection, filters: dict[str, Any], person_id: UUID) -> dict[str, Any]:
    return _person_agg(conn, "player_fielding", filters, person_id, _FIELD_SELECT,
                       lambda r: {"subject_id": str(r["subject_id"]), "matches": int(r["matches"]),
                                  "catches": int(r["catches"]), "field_catches": int(r["field_catches"]),
                                  "keeper_catches": int(r["keeper_catches"]), "stumpings": int(r["stumpings"]),
                                  "run_outs": int(r["run_outs"]), "keeper_dismissals": int(r["keeper_dismissals"])})
