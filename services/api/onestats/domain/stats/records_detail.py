"""Innings-, match- and season-level records (RMCC report catalogue §23.3/§23.6/§23.7/§23.9).

These read the **same approved match data** the engine builds on, but at a finer grain than the per-match
ledger: individual innings records (highest scores, most expensive spell, 40s/90s counts), bowler/fielder
dismissal records, player pairs, and best single-season aggregates. Approved, statistics-eligible matches
only (`official_for_stats`), merge-aware (contributions under a merged identity roll up to the canonical
person), unknown-aware (unknown runs/wickets are never treated as zero). No statistic is recomputed that
the engine already owns — this is the innings/season granularity the per-match ledger does not store.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

# canonical person id (fold a merged identity into the person it was merged into)
_CANON = "coalesce(p.merged_into_id, p.id)"
_OFFICIAL = "m.approval_status IN ('approved','verified_partial') AND m.include_in_statistics = true"


def _scope(f: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    clauses = [f"m.workspace_id = :w AND {_OFFICIAL}"]
    params: dict[str, Any] = {"w": f["workspace_id"]}
    for key, col in (("season_id", "m.season_id"), ("grade_id", "m.grade_id"),
                     ("competition_id", "m.competition_id")):
        if f.get(key):
            clauses.append(f"{col} = :{key}")
            params[key] = f[key]
    return " AND ".join(clauses), params


def _names(conn: Connection, workspace_id: UUID) -> dict[str, str]:
    return {str(r["id"]): r["display_name"] for r in conn.execute(
        text("SELECT id, display_name FROM person WHERE workspace_id = :w"), {"w": workspace_id}).mappings()}


# --- single-season best aggregates (merge-aware, from the ledger) ---------------------------------

def best_single_season(conn: Connection, f: dict[str, Any], *, discipline: str = "batting",
                       limit: int = 50) -> list[dict[str, Any]]:
    """Highest single-season run (or wicket) aggregates across all players and seasons (all-time list)."""
    calc = "player_batting" if discipline == "batting" else "player_bowling"
    metric = "runs" if discipline == "batting" else "wickets"
    where, params = _scope({k: v for k, v in f.items() if k != "season_id"})  # season is the grouping, not a filter
    params["cal"] = calc
    sql = (f"SELECT {_CANON} AS subject_id, s.label AS season, "
           f"       sum((c.metrics->>'{metric}')::int) AS value "
           "FROM match_stat_contribution c JOIN match m ON m.id = c.match_id "
           "JOIN person p ON p.id = c.subject_id JOIN season s ON s.id = c.season_id "
           f"WHERE c.calculator = :cal AND {where} "
           f"GROUP BY {_CANON}, s.label ORDER BY value DESC NULLS LAST LIMIT :lim")
    params["lim"] = limit
    names = _names(conn, f["workspace_id"])
    return [{"subject_id": str(r["subject_id"]), "player": names.get(str(r["subject_id"]), "Unknown"),
             "season": r["season"], "value": int(r["value"] or 0)}
            for r in conn.execute(text(sql), params).mappings()]


# --- individual innings / match records (from raw approved entries) -------------------------------

def highest_individual_innings(conn: Connection, f: dict[str, Any], *, limit: int = 50) -> list[dict[str, Any]]:
    where, params = _scope(f)
    params["lim"] = limit
    sql = (f"SELECT {_CANON} AS sid, be.runs AS runs, be.balls_faced AS balls, be.dismissal_type AS dt, "
           "       m.match_date AS d "
           "FROM batting_entry be JOIN innings i ON i.id = be.innings_id JOIN match m ON m.id = i.match_id "
           "JOIN person p ON p.id = be.person_id "
           f"WHERE be.person_id IS NOT NULL AND be.runs IS NOT NULL AND {where} "
           "ORDER BY be.runs DESC, be.balls_faced ASC NULLS LAST LIMIT :lim")
    names = _names(conn, f["workspace_id"])
    out = []
    for r in conn.execute(text(sql), params).mappings():
        not_out = r["dt"] in ("not_out", "retired_not_out")
        out.append({"subject_id": str(r["sid"]), "player": names.get(str(r["sid"]), "Unknown"),
                    "runs": int(r["runs"]), "not_out": not_out, "balls": r["balls"],
                    "match_date": r["d"].isoformat() if r["d"] else None})
    return out


def most_runs_in_a_match(conn: Connection, f: dict[str, Any], *, limit: int = 50) -> list[dict[str, Any]]:
    """Highest runs by a player across all innings of a single match (from the per-match ledger)."""
    where, params = _scope(f)
    params["lim"] = limit
    sql = (f"SELECT {_CANON} AS sid, max((c.metrics->>'match_runs')::int) AS runs "
           "FROM match_stat_contribution c JOIN match m ON m.id = c.match_id JOIN person p ON p.id = c.subject_id "
           f"WHERE c.calculator = 'player_batting' AND {where} "
           f"GROUP BY {_CANON} ORDER BY runs DESC NULLS LAST LIMIT :lim")
    names = _names(conn, f["workspace_id"])
    return [{"subject_id": str(r["sid"]), "player": names.get(str(r["sid"]), "Unknown"), "runs": int(r["runs"] or 0)}
            for r in conn.execute(text(sql), params).mappings()]


def best_bowling_in_match(conn: Connection, f: dict[str, Any], *, limit: int = 50) -> list[dict[str, Any]]:
    """Best bowling in a match, ranked by most wickets then FEWEST runs conceded (runs tie-break). Uses
    verified match-level bowling aggregates; runs are never invented when incomplete. Genuine ties (equal
    wickets AND runs) are preserved by stable ordering."""
    where, params = _scope(f)
    params["lim"] = limit
    # one row per (player, match): match wickets and match runs conceded (both summed across the match)
    sql = (f"SELECT {_CANON} AS sid, c.match_id AS mid, "
           "       max((c.metrics->>'match_wickets')::int) AS wkts, "
           "       sum((c.metrics->>'runs')::int) AS runs, m.match_date AS d "
           "FROM match_stat_contribution c JOIN match m ON m.id = c.match_id JOIN person p ON p.id = c.subject_id "
           f"WHERE c.calculator = 'player_bowling' AND {where} "
           f"GROUP BY {_CANON}, c.match_id, m.match_date "
           "ORDER BY wkts DESC NULLS LAST, runs ASC NULLS LAST LIMIT :lim")
    names = _names(conn, f["workspace_id"])
    return [{"subject_id": str(r["sid"]), "player": names.get(str(r["sid"]), "Unknown"),
             "wickets": int(r["wkts"] or 0), "runs": int(r["runs"]) if r["runs"] is not None else None,
             "match_date": r["d"].isoformat() if r["d"] else None}
            for r in conn.execute(text(sql), params).mappings()]


def most_expensive_innings(conn: Connection, f: dict[str, Any], *, limit: int = 50) -> list[dict[str, Any]]:
    where, params = _scope(f)
    params["lim"] = limit
    sql = (f"SELECT {_CANON} AS sid, be.runs_conceded AS runs, be.wickets AS wkts, m.match_date AS d "
           "FROM bowling_entry be JOIN innings i ON i.id = be.innings_id JOIN match m ON m.id = i.match_id "
           "JOIN person p ON p.id = be.person_id "
           f"WHERE be.person_id IS NOT NULL AND be.runs_conceded IS NOT NULL AND {where} "
           "ORDER BY be.runs_conceded DESC LIMIT :lim")
    names = _names(conn, f["workspace_id"])
    return [{"subject_id": str(r["sid"]), "player": names.get(str(r["sid"]), "Unknown"),
             "runs": int(r["runs"]), "wickets": r["wkts"],
             "match_date": r["d"].isoformat() if r["d"] else None}
            for r in conn.execute(text(sql), params).mappings()]


def most_scores_in_range(conn: Connection, f: dict[str, Any], *, lo: int, hi: int,
                         limit: int = 50) -> list[dict[str, Any]]:
    """Count innings with a score in [lo, hi] per player (e.g. 40s = 40–49, 90s = 90–99)."""
    where, params = _scope(f)
    params.update({"lo": lo, "hi": hi, "lim": limit})
    sql = (f"SELECT {_CANON} AS sid, count(*) AS n FROM batting_entry be "
           "JOIN innings i ON i.id = be.innings_id JOIN match m ON m.id = i.match_id "
           "JOIN person p ON p.id = be.person_id "
           f"WHERE be.person_id IS NOT NULL AND be.runs BETWEEN :lo AND :hi AND {where} "
           f"GROUP BY {_CANON} ORDER BY n DESC LIMIT :lim")
    names = _names(conn, f["workspace_id"])
    return [{"subject_id": str(r["sid"]), "player": names.get(str(r["sid"]), "Unknown"), "count": int(r["n"])}
            for r in conn.execute(text(sql), params).mappings()]


def most_ducks_inflicted(conn: Connection, f: dict[str, Any], *, limit: int = 50) -> list[dict[str, Any]]:
    """Count dismissals where the bowler dismissed a batter for 0 (bowler credited; run outs excluded)."""
    where, params = _scope(f)
    params["lim"] = limit
    sql = (f"SELECT coalesce(p.merged_into_id, p.id) AS sid, count(*) AS n FROM batting_entry be "
           "JOIN innings i ON i.id = be.innings_id JOIN match m ON m.id = i.match_id "
           "JOIN person p ON p.id = be.bowler_person_id "
           "WHERE be.bowler_person_id IS NOT NULL AND be.runs = 0 "
           "AND be.dismissal_type IN ('bowled','lbw','caught','caught_behind','caught_and_bowled','stumped','hit_wicket') "
           f"AND {where} GROUP BY coalesce(p.merged_into_id, p.id) ORDER BY n DESC LIMIT :lim")
    names = _names(conn, f["workspace_id"])
    return [{"subject_id": str(r["sid"]), "player": names.get(str(r["sid"]), "Unknown"), "count": int(r["n"])}
            for r in conn.execute(text(sql), params).mappings()]


def most_wk_dismissals_in_innings(conn: Connection, f: dict[str, Any], *, limit: int = 50) -> list[dict[str, Any]]:
    """Most wicketkeeping dismissals (keeper catches + stumpings) in a single innings, attributed to the
    **actual** keeper who took them (the recorded fielder), so where more than one player kept wicket in an
    innings each keeper is credited only with their own dismissals. A dismissal counts as wicketkeeping
    when it is a stumping, a caught-behind, or a catch by a recorded keeper of that side (primary OR second
    keeper); outfield catches are never counted. A keeper dismissal whose fielder is unknown is NOT guessed
    or attributed to the primary keeper — it is left out (unknown ≠ invented). No double counting."""
    where, params = _scope(f)
    params["lim"] = limit
    sql = (
        "SELECT coalesce(p.merged_into_id, p.id) AS sid, be.innings_id AS inn, m.match_date AS d, "
        "  count(*) FILTER (WHERE be.dismissal_type = 'stumped') AS st, "
        "  count(*) FILTER (WHERE be.dismissal_type IN ('caught','caught_behind')) AS ct "
        "FROM batting_entry be JOIN innings i ON i.id = be.innings_id JOIN match m ON m.id = i.match_id "
        "JOIN match_team mt ON mt.match_id = m.id AND mt.team_id = i.bowling_team_id "
        "JOIN person p ON p.id = be.fielder_person_id "
        "WHERE be.fielder_person_id IS NOT NULL AND ("
        "  be.dismissal_type IN ('stumped','caught_behind') "
        "  OR (be.dismissal_type = 'caught' AND be.fielder_person_id IN "
        "        (mt.wicketkeeper_person_id, mt.wicketkeeper2_person_id))) "
        f"AND {where} "
        "GROUP BY be.innings_id, coalesce(p.merged_into_id, p.id), m.match_date "
        "ORDER BY (count(*) FILTER (WHERE be.dismissal_type = 'stumped') + "
        "          count(*) FILTER (WHERE be.dismissal_type IN ('caught','caught_behind'))) DESC LIMIT :lim")
    names = _names(conn, f["workspace_id"])
    out = []
    for r in conn.execute(text(sql), params).mappings():
        ct, st = int(r["ct"]), int(r["st"])
        out.append({"subject_id": str(r["sid"]), "player": names.get(str(r["sid"]), "Unknown"),
                    "catches": ct, "stumpings": st, "total": ct + st,
                    "match_date": r["d"].isoformat() if r["d"] else None})
    return out


def captaincy_by_season(conn: Connection, f: dict[str, Any], *, limit: int = 500) -> list[dict[str, Any]]:
    """Per-season captaincy breakdown (one row per season × captain): results, win %, finals and grand
    finals, and premierships (grand finals won as captain — verified). From the captaincy ledger."""
    where, params = _scope({k: v for k, v in f.items() if k != "season_id"})
    params["lim"] = limit
    sql = (f"SELECT {_CANON} AS sid, s.label AS season, s.start_date AS sd, "
           "  sum((c.metrics->>'captained')::int) AS captained, sum((c.metrics->>'win')::int) AS wins, "
           "  sum((c.metrics->>'loss')::int) AS losses, sum((c.metrics->>'draw')::int) AS draws, "
           "  sum((c.metrics->>'tie')::int) AS ties, sum((c.metrics->>'no_result')::int) AS no_results, "
           "  sum((c.metrics->>'gf_captained')::int) AS gf_captained, sum((c.metrics->>'gf_win')::int) AS gf_wins "
           "FROM match_stat_contribution c JOIN match m ON m.id = c.match_id "
           "JOIN person p ON p.id = c.subject_id JOIN season s ON s.id = c.season_id "
           f"WHERE c.calculator = 'player_captaincy' AND {where} "
           f"GROUP BY {_CANON}, s.label, s.start_date ORDER BY s.start_date NULLS LAST, captained DESC LIMIT :lim")
    names = _names(conn, f["workspace_id"])
    out = []
    for r in conn.execute(text(sql), params).mappings():
        captained, wins = int(r["captained"] or 0), int(r["wins"] or 0)
        no_res = int(r["no_results"] or 0)
        eligible = captained - no_res
        out.append({"subject_id": str(r["sid"]), "season": r["season"],
                    "player": names.get(str(r["sid"]), "Unknown"), "captained": captained, "wins": wins,
                    "losses": int(r["losses"] or 0), "draws": int(r["draws"] or 0), "ties": int(r["ties"] or 0),
                    "no_results": no_res, "win_pct": round(wins * 100 / eligible, 1) if eligible else None,
                    "gf_captained": int(r["gf_captained"] or 0), "premierships": int(r["gf_wins"] or 0)})
    return out


def captaincy_comparison(conn: Connection, workspace_id: UUID, person_ids: list[UUID]) -> list[dict[str, Any]]:
    """Side-by-side captaincy figures for the selected captains (same scope for all), from the one engine.
    Includes consecutive-wins streak so the comparison matches the catalogue reports."""
    from onestats.domain.stats import engine, streaks
    f = {"workspace_id": workspace_id}
    names = _names(conn, workspace_id)
    streak_by = {r["subject_id"]: r["streak"]
                 for r in streaks.streak_leaders(conn, "player_captaincy", "wins", f)}
    out = []
    for pid in person_ids:
        c = engine.person_captaincy(conn, f, pid)
        captained, wins, no_res = c["captained"], c["wins"], c["no_results"]
        eligible = captained - no_res
        out.append({"subject_id": str(pid), "player": names.get(str(pid), "Unknown"),
                    "captained": captained, "wins": wins, "losses": c["losses"], "draws": c["draws"],
                    "ties": c["ties"], "no_results": no_res,
                    "win_pct": round(wins * 100 / eligible, 1) if eligible else None,
                    "gf_captained": c["gf_captained"], "gf_wins": c["gf_wins"],
                    "consecutive_wins": streak_by.get(str(pid), 0)})
    return out


def fielder_bowler_combinations(conn: Connection, f: dict[str, Any], *, limit: int = 50) -> list[dict[str, Any]]:
    """Dismissals crediting a specific (fielder, bowler) pair (catches/stumpings). No double counting."""
    where, params = _scope(f)
    params["lim"] = limit
    sql = ("SELECT be.fielder_person_id AS fid, be.bowler_person_id AS bid, count(*) AS n "
           "FROM batting_entry be JOIN innings i ON i.id = be.innings_id JOIN match m ON m.id = i.match_id "
           "WHERE be.fielder_person_id IS NOT NULL AND be.bowler_person_id IS NOT NULL "
           "AND be.dismissal_type IN ('caught','caught_behind','stumped') "
           f"AND {where} GROUP BY be.fielder_person_id, be.bowler_person_id ORDER BY n DESC LIMIT :lim")
    names = _names(conn, f["workspace_id"])
    return [{"fielder_name": names.get(str(r["fid"]), "Unknown"), "bowler_name": names.get(str(r["bid"]), "Unknown"),
             "count": int(r["n"])} for r in conn.execute(text(sql), params).mappings()]


# --- player pairs & service ------------------------------------------------------------------------

def most_matches_together(conn: Connection, f: dict[str, Any], *, limit: int = 50) -> list[dict[str, Any]]:
    """Unordered pairs of players by matches both appeared in (from the appearance ledger). No double count."""
    where, params = _scope(f)
    # appearance contributions carry the match; pair up players within each match
    sql = (f"SELECT c.match_id AS mid, {_CANON} AS sid FROM match_stat_contribution c "
           "JOIN match m ON m.id = c.match_id JOIN person p ON p.id = c.subject_id "
           f"WHERE c.calculator = 'player_appearance' AND {where}")
    by_match: dict[Any, set] = {}
    for r in conn.execute(text(sql), params).mappings():
        by_match.setdefault(r["mid"], set()).add(str(r["sid"]))
    pair_counts: dict[tuple[str, str], int] = {}
    for players in by_match.values():
        ordered = sorted(players)
        for a_i in range(len(ordered)):
            for b_i in range(a_i + 1, len(ordered)):
                key = (ordered[a_i], ordered[b_i])
                pair_counts[key] = pair_counts.get(key, 0) + 1
    names = _names(conn, f["workspace_id"])
    rows = [{"player1_name": names.get(a, "Unknown"), "player2_name": names.get(b, "Unknown"), "count": n}
            for (a, b), n in pair_counts.items()]
    rows.sort(key=lambda r: -r["count"])
    return rows[:limit]


def top_partnership_aggregates(conn: Connection, f: dict[str, Any], *, limit: int = 50) -> list[dict[str, Any]]:
    """Σ partnership runs for an unordered batting pair across matches (no double counting)."""
    where, params = _scope(f)
    sql = ("SELECT p1.id AS a, p2.id AS b, sum(pt.runs) AS total, count(*) AS n "
           "FROM partnership pt JOIN innings i ON i.id = pt.innings_id JOIN match m ON m.id = i.match_id "
           "JOIN person p1 ON p1.id = pt.player1_person_id JOIN person p2 ON p2.id = pt.player2_person_id "
           f"WHERE pt.runs IS NOT NULL AND pt.player1_person_id IS NOT NULL AND pt.player2_person_id IS NOT NULL "
           f"AND {where} GROUP BY p1.id, p2.id ORDER BY total DESC LIMIT :lim")
    params["lim"] = limit
    names = _names(conn, f["workspace_id"])
    out = []
    seen: set = set()
    for r in conn.execute(text(sql), params).mappings():
        key = tuple(sorted((str(r["a"]), str(r["b"]))))
        if key in seen:
            continue
        seen.add(key)
        out.append({"player1_name": names.get(str(r["a"]), "Unknown"), "player2_name": names.get(str(r["b"]), "Unknown"),
                    "total_runs": int(r["total"] or 0), "partnerships": int(r["n"])})
    return out


def longest_serving(conn: Connection, f: dict[str, Any], *, limit: int = 50) -> list[dict[str, Any]]:
    """Span from first to last appearance per player — seasons represented and years (from appearances)."""
    where, params = _scope(f)
    params["lim"] = limit
    sql = (f"SELECT {_CANON} AS sid, count(DISTINCT c.season_id) AS seasons, "
           "       min(m.match_date) AS first_d, max(m.match_date) AS last_d "
           "FROM match_stat_contribution c JOIN match m ON m.id = c.match_id JOIN person p ON p.id = c.subject_id "
           f"WHERE c.calculator = 'player_appearance' AND {where} "
           f"GROUP BY {_CANON} ORDER BY seasons DESC, (max(m.match_date) - min(m.match_date)) DESC NULLS LAST LIMIT :lim")
    names = _names(conn, f["workspace_id"])
    out = []
    for r in conn.execute(text(sql), params).mappings():
        first_d, last_d = r["first_d"], r["last_d"]
        years = round((last_d - first_d).days / 365.25, 1) if first_d and last_d else None
        out.append({"subject_id": str(r["sid"]), "player": names.get(str(r["sid"]), "Unknown"),
                    "seasons": int(r["seasons"] or 0),
                    "first": first_d.isoformat() if first_d else None,
                    "last": last_d.isoformat() if last_d else None, "span_years": years})
    return out
