"""Report catalogue (Phase 12, Stages 12.13/12.15 + catalogue expansion).

Maps report keys to the ONE statistics engine (and records/partnerships/competition-points/integrity
services) and the shared PDF builder, so every report exports to a branded, print-ready PDF whose figures
match the on-screen report exactly. Nothing here computes a statistic itself — each report is a *view*
(a metric emphasis + sort + columns) over the existing deterministic engine. No competing calculations.

Two layers:
- ``REPORTS`` — base report *types* (one per engine output shape) with their columns and data function.
- ``CATALOGUE`` — the professional library of genuinely distinct reports. Each entry reuses a base type
  with a preset metric/sort (e.g. Most Runs vs Highest Average vs Most Centuries are distinct reports).
  Scope (season/grade/competition/team/date/venue/finals) stays a *filter*, never a separate report.
"""
from __future__ import annotations

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.core.config import Settings
from onestats.domain import branding, logos
from onestats.domain.records import honours as honours_mod
from onestats.domain.records import milestones as milestones_mod
from onestats.domain.records import records as records_mod
from onestats.domain.stats import (
    competition_points,
    engine,
    integrity,
    partnerships,
    records_detail,
    streaks,
)
from onestats.reports.builder import Column, ReportDoc, Section, build_pdf

_C = Column


# --- flat-list adapters for the non-leaderboard sources (still the one engine underneath) ----------

def _partnerships_rows(conn: Connection, f: dict[str, Any], **kw: Any) -> list[dict[str, Any]]:
    return partnerships.batting_partnerships(conn, f, by_wicket=bool(kw.get("by_wicket")), limit=kw.get("limit", 50))


def _groups_rows(conn: Connection, f: dict[str, Any], **kw: Any) -> list[dict[str, Any]]:
    return partnerships.bowling_groups(conn, f, size=int(kw.get("size", 2)), limit=kw.get("limit", 50))["groups"]


def _seasonal_rows(conn: Connection, f: dict[str, Any], **kw: Any) -> list[dict[str, Any]]:
    out = []
    for s in records_mod.seasonal_leaders(conn, f["workspace_id"], competition_id=f.get("competition_id")):
        lrs, lwt = s.get("leading_run_scorer"), s.get("leading_wicket_taker")
        out.append({"label": s["label"], "run_scorer": (lrs or {}).get("player"),
                    "runs": (lrs or {}).get("value"), "wicket_taker": (lwt or {}).get("player"),
                    "wickets": (lwt or {}).get("value")})
    return out


def _honours_rows(conn: Connection, f: dict[str, Any], **kw: Any) -> list[dict[str, Any]]:
    out = []
    for h in honours_mod.list_honours(conn, f["workspace_id"], honour_type=kw.get("honour_type")):
        out.append({"person_id": str(h["person_id"]) if h.get("person_id") else None, "title": h.get("title"),
                    "category": h.get("award_category") or (h.get("honour_type") or "").replace("_", " "),
                    "awarded_season": h.get("awarded_season") or "—"})
    return out


def _milestones_rows(conn: Connection, f: dict[str, Any], **kw: Any) -> list[dict[str, Any]]:
    rows = milestones_mod.upcoming_for_workspace(conn, f["workspace_id"], window=int(kw.get("window", 25)))
    return [{"person_id": r["person_id"], "metric": r["metric"], "current": r["current"],
             "threshold": r["threshold"], "to_go": r["to_go"]} for r in rows]


def _integrity_rows(conn: Connection, f: dict[str, Any], **kw: Any) -> list[dict[str, Any]]:
    return integrity.workspace_integrity(conn, f["workspace_id"]).get("reconcile_issues", [])


# --- base report types (one per engine output shape) ----------------------------------------------

_BAT_COLS = [_C("rank", "#", "right"), _C("player", "Player"), _C("matches", "M", "right"),
             _C("innings", "Inns", "right"), _C("not_outs", "NO", "right"), _C("runs", "Runs", "right"),
             _C("highest_score", "HS", "right"), _C("average", "Avg", "right", 2),
             _C("strike_rate", "SR", "right", 2), _C("fifties", "50s", "right"),
             _C("hundreds", "100s", "right"), _C("fours", "4s", "right"), _C("sixes", "6s", "right"),
             _C("ducks", "0s", "right")]
_BOWL_COLS = [_C("rank", "#", "right"), _C("player", "Player"), _C("matches", "M", "right"),
              _C("overs", "Overs", "right", 1), _C("maidens", "Mdns", "right"), _C("runs", "Runs", "right"),
              _C("wickets", "Wkts", "right"), _C("best_match_wickets", "Best", "right"),
              _C("average", "Avg", "right", 2), _C("economy", "Econ", "right", 2),
              _C("strike_rate", "SR", "right", 2), _C("five_wkt_innings", "5wi", "right")]
_FIELD_COLS = [_C("rank", "#", "right"), _C("player", "Player"), _C("matches", "M", "right"),
               _C("catches", "Ct", "right"), _C("field_catches", "Ct (field)", "right"),
               _C("keeper_catches", "Ct (wk)", "right"), _C("stumpings", "St", "right"),
               _C("run_outs", "RO", "right"), _C("keeper_dismissals", "WK Dis", "right")]
_CAPT_COLS = [_C("rank", "#", "right"), _C("player", "Captain"), _C("captained", "M", "right"),
              _C("wins", "W", "right"), _C("losses", "L", "right"), _C("draws", "D", "right"),
              _C("ties", "T", "right"), _C("win_pct", "Win %", "right", 1),
              _C("gf_captained", "GF", "right"), _C("gf_wins", "GF W", "right")]
_PART_COLS = [_C("rank", "#", "right"), _C("player", "Player"), _C("matches", "M", "right"),
              _C("wins", "W", "right"), _C("losses", "L", "right")]
_TEAM_COLS = [_C("rank", "#", "right"), _C("team", "Team"), _C("played", "P", "right"),
              _C("wins", "W", "right"), _C("losses", "L", "right"), _C("draws", "D", "right"),
              _C("ties", "T", "right"), _C("win_pct", "Win %", "right", 1)]

REPORTS: dict[str, dict[str, Any]] = {
    "batting": {"title": "Batting — Leading Run Scorers", "columns": _BAT_COLS,
                "fn": lambda conn, f, **kw: engine.batting_leaders(conn, f, order_by=kw.get("order_by", "runs"),
                                                                   limit=kw.get("limit", 100), min_runs=kw.get("min_runs"))},
    "bowling": {"title": "Bowling — Leading Wicket Takers", "columns": _BOWL_COLS,
                "fn": lambda conn, f, **kw: engine.bowling_leaders(conn, f, order_by=kw.get("order_by", "wickets"),
                                                                   limit=kw.get("limit", 100),
                                                                   over_length=kw.get("over_length", 6),
                                                                   min_wickets=kw.get("min_wickets"))},
    "fielding": {"title": "Fielding & Wicketkeeping", "columns": _FIELD_COLS,
                 "fn": lambda conn, f, **kw: engine.fielding_leaders(conn, f, order_by=kw.get("order_by", "catches"),
                                                                     limit=kw.get("limit", 100))},
    "captaincy": {"title": "Captaincy Records", "columns": _CAPT_COLS,
                  "fn": lambda conn, f, **kw: engine.captaincy_leaders(conn, f, order_by=kw.get("order_by", "captained"),
                                                                       limit=kw.get("limit", 100),
                                                                       min_eligible=kw.get("min_eligible", 20))},
    "participation": {"title": "Player Appearances", "columns": _PART_COLS,
                      "fn": lambda conn, f, **kw: engine.participation_leaders(conn, f, order_by=kw.get("order_by", "matches"),
                                                                               limit=kw.get("limit", 100))},
    "teams": {"title": "Team Records", "columns": _TEAM_COLS,
              "fn": lambda conn, f, **kw: engine.team_records(conn, f, order_by=kw.get("order_by", "wins"),
                                                              limit=kw.get("limit", 100))},
    "partnerships": {"title": "Highest Partnerships",
                     "columns": [_C("rank", "#", "right"), _C("wicket", "Wkt", "right"), _C("runs", "Runs", "right"),
                                 _C("batter1_name", "Batter 1"), _C("batter2_name", "Batter 2"),
                                 _C("unbroken", "Unbroken"), _C("match_date", "Date")],
                     "fn": _partnerships_rows},
    "bowling_groups": {"title": "Bowling Partnerships (Groups)",
                       "columns": [_C("rank", "#", "right"), _C("members_names", "Bowlers"),
                                   _C("matches_together", "Matches", "right"), _C("total_wickets", "Wkts", "right"),
                                   _C("avg_per_match", "Avg/Match", "right", 2), _C("known_minimum", "Known min.")],
                       "fn": _groups_rows},
    "seasonal_leaders": {"title": "Seasonal Leaders",
                         "columns": [_C("label", "Season"), _C("run_scorer", "Leading Run Scorer"),
                                     _C("runs", "Runs", "right"), _C("wicket_taker", "Leading Wicket Taker"),
                                     _C("wickets", "Wkts", "right")],
                         "fn": _seasonal_rows},
    "honours": {"title": "Awards & Honours",
                "columns": [_C("person_name", "Recipient"), _C("title", "Award"), _C("category", "Category"),
                            _C("awarded_season", "Season")],
                "fn": _honours_rows},
    "milestones_upcoming": {"title": "Upcoming Milestones",
                            "columns": [_C("person_name", "Player"), _C("metric", "Metric"),
                                        _C("current", "Current", "right"), _C("threshold", "Milestone", "right"),
                                        _C("to_go", "To go", "right")],
                            "fn": _milestones_rows},
    "integrity": {"title": "Data Integrity — Reconciliation Issues",
                  "columns": [_C("match_id", "Match"), _C("status", "Status"),
                              _C("recorded", "Recorded Wkts", "right"), _C("from_dismissals", "From Dismissals", "right")],
                  "fn": _integrity_rows},
    # --- consecutive records (streaks) ---
    "streak_team": {"title": "Team Streaks", "columns": [
        _C("rank", "#", "right"), _C("team", "Team"), _C("streak", "Streak", "right"),
        _C("matches", "Matches", "right"), _C("known_minimum", "Known min.")],
        "fn": lambda conn, f, **kw: streaks.streak_leaders(conn, "team_result", kw.get("kind", "wins"), f)},
    "streak_captaincy": {"title": "Captaincy Streaks", "columns": [
        _C("rank", "#", "right"), _C("player", "Captain"), _C("streak", "Streak", "right"),
        _C("matches", "Matches", "right"), _C("known_minimum", "Known min.")],
        "fn": lambda conn, f, **kw: streaks.streak_leaders(conn, "player_captaincy", kw.get("kind", "wins"), f)},
    # --- single-season best aggregates ---
    "best_season": {"title": "Best Single-Season Aggregates", "columns": [
        _C("rank", "#", "right"), _C("player", "Player"), _C("season", "Season"), _C("value", "Total", "right")],
        "fn": lambda conn, f, **kw: records_detail.best_single_season(conn, f, discipline=kw.get("discipline", "batting"))},
    # --- individual innings / match records ---
    "highest_innings": {"title": "Highest Individual Scores", "columns": [
        _C("rank", "#", "right"), _C("player", "Player"), _C("runs", "Score", "right"),
        _C("not_out", "NO"), _C("balls", "Balls", "right"), _C("match_date", "Date")],
        "fn": lambda conn, f, **kw: records_detail.highest_individual_innings(conn, f)},
    "runs_in_match": {"title": "Most Runs in a Match", "columns": [
        _C("rank", "#", "right"), _C("player", "Player"), _C("runs", "Runs", "right")],
        "fn": lambda conn, f, **kw: records_detail.most_runs_in_a_match(conn, f)},
    "expensive_innings": {"title": "Most Expensive Bowling in an Innings", "columns": [
        _C("rank", "#", "right"), _C("player", "Player"), _C("runs", "Runs", "right"),
        _C("wickets", "Wkts", "right"), _C("match_date", "Date")],
        "fn": lambda conn, f, **kw: records_detail.most_expensive_innings(conn, f)},
    "scores_range": {"title": "Scores in Range", "columns": [
        _C("rank", "#", "right"), _C("player", "Player"), _C("count", "Count", "right")],
        "fn": lambda conn, f, **kw: records_detail.most_scores_in_range(conn, f, lo=kw.get("lo", 40), hi=kw.get("hi", 49))},
    "ducks_inflicted": {"title": "Most Ducks Inflicted (Bowlers)", "columns": [
        _C("rank", "#", "right"), _C("player", "Bowler"), _C("count", "Ducks", "right")],
        "fn": lambda conn, f, **kw: records_detail.most_ducks_inflicted(conn, f)},
    "fielder_bowler": {"title": "Top Fielder–Bowler Combinations", "columns": [
        _C("rank", "#", "right"), _C("fielder_name", "Fielder"), _C("bowler_name", "Bowler"), _C("count", "Dismissals", "right")],
        "fn": lambda conn, f, **kw: records_detail.fielder_bowler_combinations(conn, f)},
    "matches_together": {"title": "Most Matches Played Together", "columns": [
        _C("rank", "#", "right"), _C("player1_name", "Player 1"), _C("player2_name", "Player 2"), _C("count", "Matches", "right")],
        "fn": lambda conn, f, **kw: records_detail.most_matches_together(conn, f)},
    "partnership_aggregates": {"title": "Top Partnership Aggregates (Pairs)", "columns": [
        _C("rank", "#", "right"), _C("player1_name", "Batter 1"), _C("player2_name", "Batter 2"),
        _C("total_runs", "Total Runs", "right"), _C("partnerships", "Partnerships", "right")],
        "fn": lambda conn, f, **kw: records_detail.top_partnership_aggregates(conn, f)},
    "longest_serving": {"title": "Longest-Serving Players", "columns": [
        _C("rank", "#", "right"), _C("player", "Player"), _C("seasons", "Seasons", "right"),
        _C("span_years", "Years", "right", 1), _C("first", "First"), _C("last", "Last")],
        "fn": lambda conn, f, **kw: records_detail.longest_serving(conn, f)},
    # --- consecutive matches (over the team's played-fixture sequence) ---
    "player_streak": {"title": "Most Consecutive Matches Played", "columns": [
        _C("rank", "#", "right"), _C("player", "Player"), _C("team_name", "Team"), _C("streak", "Streak", "right"),
        _C("start_season", "From"), _C("end_season", "To"), _C("start_date", "Start"), _C("end_date", "End"),
        _C("known_minimum", "Known min.")],
        "fn": lambda conn, f, **kw: streaks.player_match_streaks(conn, f, "played")},
    "captain_match_streak": {"title": "Most Consecutive Matches Captained", "columns": [
        _C("rank", "#", "right"), _C("player", "Captain"), _C("team_name", "Team"), _C("streak", "Streak", "right"),
        _C("start_season", "From"), _C("end_season", "To"), _C("start_date", "Start"), _C("end_date", "End"),
        _C("known_minimum", "Known min.")],
        "fn": lambda conn, f, **kw: streaks.player_match_streaks(conn, f, "captained")},
    "without_duck": {"title": "Most Consecutive Scores Without a Duck", "columns": [
        _C("rank", "#", "right"), _C("player", "Player"), _C("streak", "Innings", "right"), _C("known_minimum", "Known min.")],
        "fn": lambda conn, f, **kw: streaks.without_duck_streaks(conn, f)},
    # --- wicketkeeping in an innings & best bowling in a match (runs tie-break) ---
    "wk_innings": {"title": "Most Wicketkeeping Dismissals in an Innings", "columns": [
        _C("rank", "#", "right"), _C("player", "Wicketkeeper"), _C("catches", "Ct", "right"),
        _C("stumpings", "St", "right"), _C("total", "Total", "right"), _C("match_date", "Date")],
        "fn": lambda conn, f, **kw: records_detail.most_wk_dismissals_in_innings(conn, f)},
    "best_bowling_match": {"title": "Best Bowling in a Match", "columns": [
        _C("rank", "#", "right"), _C("player", "Player"), _C("wickets", "Wkts", "right"),
        _C("runs", "Runs", "right"), _C("match_date", "Date")],
        "fn": lambda conn, f, **kw: records_detail.best_bowling_in_match(conn, f)},
    # --- captaincy by season & comparison ---
    "captaincy_season": {"title": "Captaincy by Season", "columns": [
        _C("season", "Season"), _C("player", "Captain"), _C("captained", "M", "right"), _C("wins", "W", "right"),
        _C("losses", "L", "right"), _C("draws", "D", "right"), _C("ties", "T", "right"),
        _C("no_results", "NR", "right"), _C("win_pct", "Win %", "right", 1), _C("gf_captained", "GF", "right"),
        _C("premierships", "Prem", "right")],
        "fn": lambda conn, f, **kw: records_detail.captaincy_by_season(conn, f)},
    "captaincy_compare": {"title": "Captaincy Comparison", "columns": [
        _C("player", "Captain"), _C("captained", "M", "right"), _C("wins", "W", "right"),
        _C("losses", "L", "right"), _C("win_pct", "Win %", "right", 1), _C("consecutive_wins", "Streak", "right")],
        "fn": lambda conn, f, **kw: []},  # interactive: see the Captaincy Comparison tool / compare endpoint
}


# --- the professional catalogue (distinct reports over the base types) -----------------------------

@dataclass
class CatEntry:
    id: str
    name: str
    category: str
    description: str
    report: str                                   # base type in REPORTS
    params: dict[str, Any] = field(default_factory=dict)
    filters: tuple[str, ...] = ()
    qualification: str | None = None
    limitations: str | None = None
    rerank: tuple[str, str] | None = None         # (metric, "asc"|"desc") re-sort among qualified
    split_default: str | None = None              # a preset scope FILTER (finals/grand_final/home_away)
    csv: bool = True
    pdf: bool = True


# Standard filter sets (names only — the engine applies them).
_SCOPE = ("season", "grade", "competition", "team", "date_range", "format", "venue", "split")
_SCOPE_NO_VENUE = ("season", "grade", "competition", "team", "date_range", "split")
_QUAL_BAT = "Average/strike-rate reports qualify players by a minimum run threshold; others are kept but flagged unqualified."
_QUAL_BOWL = "Average/economy/strike-rate reports qualify players by a minimum wicket threshold; others are kept but flagged."
_KNOWN_MIN = "Totals from scorecards with unknown balls/runs are a known-minimum; unknown is never treated as zero."

CATALOGUE: list[CatEntry] = [
    # ---- Batting ----
    CatEntry("bat_most_runs", "Most Runs", "Batting", "Leading run scorers by total career/scope runs.",
             "batting", {"order_by": "runs"}, _SCOPE, limitations=_KNOWN_MIN),
    CatEntry("bat_highest_average", "Highest Batting Average", "Batting",
             "Best batting average (runs ÷ dismissals) among qualified batters (RMCC default min 500 runs).",
             "batting", {"order_by": "runs", "min_runs": 500, "limit": 1000}, _SCOPE,
             qualification=_QUAL_BAT, rerank=("average", "desc")),
    CatEntry("bat_best_strike_rate", "Best Strike Rate", "Batting",
             "Highest strike rate (runs per 100 balls) among qualified batters, over recorded balls only.",
             "batting", {"order_by": "runs", "min_runs": 100, "limit": 1000}, _SCOPE,
             qualification=_QUAL_BAT, rerank=("strike_rate", "desc"), limitations=_KNOWN_MIN),
    CatEntry("bat_highest_score", "Highest Individual Scores", "Batting",
             "Best individual innings scores.", "batting", {"order_by": "highest_score"}, _SCOPE),
    CatEntry("bat_most_centuries", "Most Centuries", "Batting", "Most hundreds scored.",
             "batting", {"order_by": "hundreds"}, _SCOPE),
    CatEntry("bat_most_fifties", "Most Half-Centuries", "Batting", "Most fifties (50–99) scored.",
             "batting", {"order_by": "fifties"}, _SCOPE),
    CatEntry("bat_most_fours", "Most Fours", "Batting", "Most boundary fours (where recorded).",
             "batting", {"order_by": "fours"}, _SCOPE, limitations="Only counts matches where boundaries were recorded."),
    CatEntry("bat_most_sixes", "Most Sixes", "Batting", "Most sixes (where recorded).",
             "batting", {"order_by": "sixes"}, _SCOPE, limitations="Only counts matches where boundaries were recorded."),
    CatEntry("bat_most_not_outs", "Most Not Outs", "Batting", "Most not-out innings.",
             "batting", {"order_by": "not_outs"}, _SCOPE),
    CatEntry("bat_most_ducks", "Most Ducks", "Batting", "Most dismissals for nought.",
             "batting", {"order_by": "ducks"}, _SCOPE),
    CatEntry("bat_consec_no_duck", "Most Consecutive Scores Without a Duck", "Batting",
             "Longest run of completed innings without a duck (a not-out is not a duck; DNB excluded).",
             "without_duck", {}, ("season", "grade", "competition"),
             limitations="Unknown-run innings break the known run and flag a known-minimum."),
    CatEntry("bat_most_innings", "Most Innings Batted", "Batting", "Most innings batted.",
             "batting", {"order_by": "innings"}, _SCOPE),
    CatEntry("bat_most_boundaries", "Most Boundaries", "Batting", "Most boundaries (fours + sixes), where recorded.",
             "batting", {"order_by": "boundaries"}, _SCOPE,
             limitations="Only counts matches where boundaries were recorded."),
    CatEntry("bat_most_runs_season", "Most Runs in a Season", "Batting",
             "Highest single-season run aggregates (all-time list; seasons never combined).",
             "best_season", {"discipline": "batting"}, ("competition", "grade")),
    CatEntry("bat_top_scores", "Top Run Scores (innings)", "Batting",
             "The highest individual innings scores on record (individual No. 1 and the list below).",
             "highest_innings", {}, ("season", "grade", "competition", "split"), limitations=_KNOWN_MIN),
    CatEntry("bat_most_runs_match", "Most Runs in a Match", "Batting",
             "Highest runs by a player across all innings of a single match.", "runs_in_match", {},
             ("season", "grade", "competition", "split")),
    CatEntry("bat_most_90s", "Most Scores in the 90s", "Batting", "Innings scored between 90 and 99.",
             "scores_range", {"lo": 90, "hi": 99}, ("season", "grade", "competition", "split")),
    CatEntry("bat_most_40s", "Most Scores in the 40s", "Batting", "Innings scored between 40 and 49 (distinct from 50s).",
             "scores_range", {"lo": 40, "hi": 49}, ("season", "grade", "competition", "split")),
    # ---- Bowling ----
    CatEntry("bowl_most_wickets", "Most Wickets", "Bowling", "Leading wicket takers.",
             "bowling", {"order_by": "wickets"}, _SCOPE, limitations=_KNOWN_MIN),
    CatEntry("bowl_best_average", "Best Bowling Average", "Bowling",
             "Lowest bowling average (runs ÷ wickets) among qualified bowlers (RMCC default min 50 wickets).",
             "bowling", {"order_by": "wickets", "min_wickets": 50, "limit": 1000}, _SCOPE,
             qualification=_QUAL_BOWL, rerank=("average", "asc")),
    CatEntry("bowl_best_economy", "Best Economy Rate", "Bowling",
             "Lowest economy (runs per over, using the configured over length) among qualified bowlers.",
             "bowling", {"order_by": "wickets", "min_wickets": 50, "limit": 1000}, _SCOPE,
             qualification=_QUAL_BOWL, rerank=("economy", "asc"),
             limitations="Economy uses the configured over length; career figures assume a single over length."),
    CatEntry("bowl_best_strike_rate", "Best Bowling Strike Rate", "Bowling",
             "Fewest balls per wicket among qualified bowlers (RMCC default min 50 wickets).",
             "bowling", {"order_by": "wickets", "min_wickets": 50, "limit": 1000}, _SCOPE,
             qualification=_QUAL_BOWL, rerank=("strike_rate", "asc")),
    CatEntry("bowl_most_five_fors", "Most Five-Wicket Innings", "Bowling", "Most five-wicket innings.",
             "bowling", {"order_by": "five_wkt_innings"}, _SCOPE),
    CatEntry("bowl_best_match", "Best Bowling in a Match", "Bowling",
             "Best bowling figures in a match — most wickets, then fewest runs conceded (runs tie-break).",
             "best_bowling_match", {}, ("season", "grade", "competition", "split"),
             limitations="Runs are never invented when incomplete; genuine ties (equal wickets and runs) are preserved."),
    CatEntry("bowl_most_maidens", "Most Maidens", "Bowling", "Most maiden overs bowled.",
             "bowling", {"order_by": "maidens"}, _SCOPE),
    CatEntry("bowl_most_overs", "Most Overs Bowled", "Bowling", "Most deliveries bowled (by balls).",
             "bowling", {"order_by": "balls"}, _SCOPE),
    CatEntry("bowl_most_wickets_season", "Most Wickets in a Season", "Bowling",
             "Highest single-season wicket aggregates (all-time list; seasons never combined).",
             "best_season", {"discipline": "bowling"}, ("competition", "grade")),
    CatEntry("bowl_most_expensive", "Most Expensive Bowling in an Innings", "Bowling",
             "Highest runs conceded in a single bowling spell.", "expensive_innings", {},
             ("season", "grade", "competition", "split")),
    CatEntry("bowl_most_ducks_inflicted", "Most Ducks Inflicted", "Bowling",
             "Most batters dismissed for nought by the bowler (run outs excluded).", "ducks_inflicted", {},
             ("season", "grade", "competition", "split")),
    # ---- Fielding ----
    CatEntry("field_most_catches", "Most Catches (all)", "Fielding", "Most catches, including keeper catches.",
             "fielding", {"order_by": "catches"}, _SCOPE_NO_VENUE),
    CatEntry("field_most_outfield", "Most Outfield Catches", "Fielding", "Most catches taken in the field (non-keeper).",
             "fielding", {"order_by": "field_catches"}, _SCOPE_NO_VENUE),
    CatEntry("field_most_run_outs", "Most Run Outs", "Fielding", "Most run-out involvements credited.",
             "fielding", {"order_by": "run_outs"}, _SCOPE_NO_VENUE,
             limitations="One fielder is credited per run out; shared involvements are not separately recorded."),
    CatEntry("field_bowler_combos", "Top Fielder–Bowler Combinations", "Fielding",
             "Most dismissals crediting a specific fielder and bowler together (catches/stumpings).",
             "fielder_bowler", {}, ("season", "grade", "competition", "split"),
             limitations="Unknown fielder or bowler is excluded (never guessed)."),
    # ---- Wicketkeeping ----
    CatEntry("wk_most_dismissals", "Most Wicketkeeping Dismissals", "Wicketkeeping",
             "Most keeper dismissals (keeper catches + stumpings).", "fielding", {"order_by": "keeper_dismissals"},
             _SCOPE_NO_VENUE),
    CatEntry("wk_most_catches", "Most Wicketkeeping Catches", "Wicketkeeping", "Most catches taken as wicketkeeper.",
             "fielding", {"order_by": "keeper_catches"}, _SCOPE_NO_VENUE),
    CatEntry("wk_most_stumpings", "Most Stumpings", "Wicketkeeping", "Most stumpings.",
             "fielding", {"order_by": "stumpings"}, _SCOPE_NO_VENUE),
    CatEntry("wk_best_innings", "Most Wicketkeeping Dismissals in an Innings", "Wicketkeeping",
             "Most keeper dismissals (catches + stumpings) in a single innings; outfield catches excluded.",
             "wk_innings", {}, ("season", "grade", "competition", "split")),
    # ---- Captaincy ----
    CatEntry("capt_most_matches", "Most Matches Captained", "Captaincy", "Most matches as credited captain.",
             "captaincy", {"order_by": "captained", "min_eligible": 0}, _SCOPE_NO_VENUE),
    CatEntry("capt_most_wins", "Most Wins as Captain", "Captaincy", "Most wins as captain.",
             "captaincy", {"order_by": "wins", "min_eligible": 0}, _SCOPE_NO_VENUE),
    CatEntry("capt_best_win_pct", "Best Captaincy Win %", "Captaincy",
             "Highest win percentage (wins ÷ eligible matches) among qualified captains (RMCC default min 20 eligible).",
             "captaincy", {"order_by": "captained", "min_eligible": 20, "limit": 1000}, _SCOPE_NO_VENUE,
             qualification="Qualified by a minimum number of eligible matches captained (no-results excluded); configurable.",
             rerank=("win_pct", "desc")),
    CatEntry("capt_most_gf", "Most Grand Finals Captained", "Captaincy", "Most grand finals as credited captain.",
             "captaincy", {"order_by": "gf_captained", "min_eligible": 0}, _SCOPE_NO_VENUE),
    CatEntry("capt_most_gf_wins", "Most Grand Final Wins as Captain", "Captaincy", "Most grand finals won as captain.",
             "captaincy", {"order_by": "gf_wins", "min_eligible": 0}, _SCOPE_NO_VENUE),
    CatEntry("capt_consec_wins", "Most Consecutive Wins as Captain", "Captaincy",
             "Longest run of wins over the captain's chronological captained-match sequence.",
             "streak_captaincy", {"kind": "wins"}, _SCOPE_NO_VENUE,
             limitations="Unknown results break the known sequence and flag a known-minimum; no-results are skipped."),
    CatEntry("capt_unbeaten", "Longest Captaincy Unbeaten Streak", "Captaincy",
             "Longest run of captained matches without a loss.", "streak_captaincy", {"kind": "unbeaten"},
             _SCOPE_NO_VENUE),
    CatEntry("capt_winless", "Longest Captaincy Winless Streak", "Captaincy",
             "Longest run of captained matches without a win.", "streak_captaincy", {"kind": "winless"},
             _SCOPE_NO_VENUE),
    CatEntry("capt_consec_matches", "Most Consecutive Matches Captained", "Captaincy",
             "Longest run of consecutive team matches the person captained (actual recorded captaincy).",
             "captain_match_streak", {}, ("season", "grade", "competition"),
             limitations="Over the team's played fixtures; no-play forfeits are skipped; undated matches flag a known-minimum."),
    CatEntry("capt_by_season", "Captaincy by Season", "Captaincy",
             "Per-season captaincy breakdown: results, win %, finals, grand finals and premierships as captain.",
             "captaincy_season", {}, ("competition", "grade")),
    CatEntry("capt_compare", "Captaincy Comparison", "Captaincy",
             "Compare two or more captains side by side (matches, W/L/D/T, win %, streaks, finals).",
             "captaincy_compare", {}, ("season", "grade", "competition")),
    # ---- Player Participation ----
    CatEntry("part_most_matches", "Most Appearances", "Player Participation", "Most matches played.",
             "participation", {"order_by": "matches"}, _SCOPE_NO_VENUE),
    CatEntry("part_most_wins", "Most Wins (player)", "Player Participation", "Most matches won while playing.",
             "participation", {"order_by": "wins"}, _SCOPE_NO_VENUE),
    CatEntry("part_longest_serving", "Longest-Serving Players", "Player Participation",
             "Span from first to last appearance — seasons represented and years (from appearances, not DOB).",
             "longest_serving", {}, ("competition", "grade")),
    CatEntry("part_matches_together", "Most Matches Played Together", "Player Participation",
             "Pairs of players who appeared in the most matches together (unordered pair; no double counting).",
             "matches_together", {}, ("season", "grade", "competition", "split")),
    CatEntry("part_consec_matches", "Most Consecutive Matches Played", "Player Participation",
             "Longest run of consecutive team matches a player appeared in (individual appearance streak).",
             "player_streak", {}, ("season", "grade", "competition"),
             limitations="Over the team's played fixtures; a missed recorded match breaks the run; undated matches flag a known-minimum."),
    # ---- Teams ----
    CatEntry("team_most_wins", "Most Wins (team)", "Teams", "Teams by total wins.",
             "teams", {"order_by": "wins"}, ("season", "grade", "competition", "split")),
    CatEntry("team_best_win_pct", "Best Team Win %", "Teams", "Teams by win percentage (results excl. no-results).",
             "teams", {"order_by": "wins", "limit": 1000}, ("season", "grade", "competition", "split"),
             rerank=("win_pct", "desc")),
    CatEntry("team_most_played", "Most Matches (team)", "Teams", "Teams by matches played.",
             "teams", {"order_by": "played"}, ("season", "grade", "competition", "split")),
    CatEntry("team_consec_wins", "Most Consecutive Wins", "Teams",
             "Longest run of consecutive wins over the team's chronological match sequence.",
             "streak_team", {"kind": "wins"}, ("season", "grade", "competition", "split"),
             limitations="No-results/abandoned are skipped; unknown results break the known run and flag a known-minimum."),
    CatEntry("team_consec_losses", "Most Consecutive Losses", "Teams",
             "Longest run of consecutive losses.", "streak_team", {"kind": "losses"},
             ("season", "grade", "competition", "split")),
    CatEntry("team_unbeaten", "Longest Unbeaten Streak", "Teams",
             "Longest run of matches without a loss (wins, draws and ties continue it).",
             "streak_team", {"kind": "unbeaten"}, ("season", "grade", "competition", "split")),
    CatEntry("team_winless", "Longest Winless Streak", "Teams",
             "Longest run of matches without a win.", "streak_team", {"kind": "winless"},
             ("season", "grade", "competition", "split")),
    # ---- Partnerships ----
    CatEntry("part_highest", "Highest Partnerships", "Partnerships", "Highest batting partnerships recorded.",
             "partnerships", {"by_wicket": False}, ("season", "grade", "competition"),
             limitations="From recorded or fall-of-wicket-derived partnerships; unknown-run partnerships excluded."),
    CatEntry("part_by_wicket", "Best Partnership per Wicket", "Partnerships",
             "The highest partnership for each wicket (1st–10th).", "partnerships", {"by_wicket": True},
             ("season", "grade", "competition")),
    CatEntry("bowl_pairs", "Bowling Pairs (combined wickets)", "Partnerships",
             "Two-bowler groups ranked by combined wickets in matches both played (D12 method).",
             "bowling_groups", {"size": 2}, _SCOPE_NO_VENUE,
             limitations="Same-match combined bowler wickets (run outs excluded); not a consecutive-over partnership."),
    CatEntry("bowl_trios", "Bowling Trios (combined wickets)", "Partnerships",
             "Three-bowler groups ranked by combined wickets in matches all played (D12 method).",
             "bowling_groups", {"size": 3}, _SCOPE_NO_VENUE),
    CatEntry("bowl_quartets", "Bowling Quartets (combined wickets)", "Partnerships",
             "Four-bowler groups ranked by combined wickets in matches all played (D12 method).",
             "bowling_groups", {"size": 4}, _SCOPE_NO_VENUE),
    CatEntry("part_aggregates", "Top Partnership Aggregates (Pairs)", "Partnerships",
             "Σ partnership runs for an unordered batting pair across matches (no double counting).",
             "partnership_aggregates", {}, ("season", "grade", "competition")),
    # ---- Seasons ----
    CatEntry("seasonal_leaders", "Seasonal Leaders", "Seasons",
             "Leading run scorer and wicket taker for each season (seasons never combined).",
             "seasonal_leaders", {}, ("competition",)),
    # ---- Finals & Grand Finals (preset scope filters over the leaderboards) ----
    CatEntry("gf_batting", "Grand Final — Batting", "Finals & Grand Finals",
             "Leading run scorers in grand finals (the batting report with the Grand Final filter preset).",
             "batting", {"order_by": "runs"}, _SCOPE, split_default="grand_final"),
    CatEntry("gf_bowling", "Grand Final — Bowling", "Finals & Grand Finals",
             "Leading wicket takers in grand finals (the bowling report with the Grand Final filter preset).",
             "bowling", {"order_by": "wickets"}, _SCOPE, split_default="grand_final"),
    CatEntry("finals_batting", "Finals — Batting", "Finals & Grand Finals",
             "Leading run scorers in finals (the batting report with the Finals filter preset).",
             "batting", {"order_by": "runs"}, _SCOPE, split_default="finals"),
    CatEntry("finals_bowling", "Finals — Bowling", "Finals & Grand Finals",
             "Leading wicket takers in finals (the bowling report with the Finals filter preset).",
             "bowling", {"order_by": "wickets"}, _SCOPE, split_default="finals"),
    # ---- Historical Records ----
    CatEntry("rec_most_runs", "All-Time Leading Run Scorers", "Historical Records",
             "Career run-scoring record holders (No. 1 and the chasing field).", "batting", {"order_by": "runs"}, _SCOPE),
    CatEntry("rec_most_wickets", "All-Time Leading Wicket Takers", "Historical Records",
             "Career wicket-taking record holders.", "bowling", {"order_by": "wickets"}, _SCOPE),
    CatEntry("rec_highest_scores", "All-Time Highest Scores", "Historical Records",
             "The highest individual innings on record.", "highest_innings", {},
             ("season", "grade", "competition", "split")),
    CatEntry("rec_best_season_runs", "Best Single-Season Run Totals", "Historical Records",
             "Highest run aggregate in a single season, all-time.", "best_season", {"discipline": "batting"},
             ("competition", "grade")),
    CatEntry("rec_best_season_wkts", "Best Single-Season Wicket Totals", "Historical Records",
             "Highest wicket aggregate in a single season, all-time.", "best_season", {"discipline": "bowling"},
             ("competition", "grade")),
    # ---- Awards & Achievements ----
    CatEntry("honours_all", "Awards & Honours", "Awards & Achievements",
             "Recorded awards, Life Members and honorary recognition (authorised, never inferred).",
             "honours", {}, (), csv=True),
    CatEntry("milestones_upcoming", "Upcoming Milestones", "Awards & Achievements",
             "Players approaching a career milestone, from confirmed totals only.",
             "milestones_upcoming", {}, (), limitations="From confirmed totals only; known-minimums never predict."),
    # ---- Data Integrity & Audit ----
    CatEntry("integrity_recon", "Data Integrity — Reconciliation", "Data Integrity & Audit",
             "Innings where recorded wickets do not match the dismissals on the scorecard (not auto-corrected).",
             "integrity", {}, (), csv=True),
]

CAT_BY_ID = {e.id: e for e in CATALOGUE}
CATEGORY_ORDER = ["Batting", "Bowling", "Fielding", "Wicketkeeping", "Captaincy", "Partnerships",
                  "Player Participation", "Teams", "Matches", "Competitions & Ladders", "Seasons",
                  "Finals & Grand Finals", "Historical Records", "Awards & Achievements",
                  "Data Integrity & Audit", "Custom Reports"]


def catalogue_metadata() -> dict[str, Any]:
    """The full catalogue for the UI: categories (in order) each with their report entries."""
    by_cat: dict[str, list[dict[str, Any]]] = {c: [] for c in CATEGORY_ORDER}
    for e in CATALOGUE:
        by_cat.setdefault(e.category, []).append({
            "id": e.id, "name": e.name, "category": e.category, "description": e.description,
            "filters": list(e.filters), "qualification": e.qualification, "limitations": e.limitations,
            "split_default": e.split_default, "csv": e.csv, "pdf": e.pdf})
    categories = [{"category": c, "reports": by_cat[c]} for c in CATEGORY_ORDER if by_cat.get(c)]
    return {"categories": categories, "count": len(CATALOGUE)}


# --- resolution + enrichment ----------------------------------------------------------------------

def _resolve(report: str) -> tuple[str, CatEntry | None, str, list[Column]]:
    """Return (base_type, entry_or_None, title, columns) for a catalogue id or a base type key."""
    if report in CAT_BY_ID:
        e = CAT_BY_ID[report]
        base = REPORTS[e.report]
        return e.report, e, e.name, base["columns"]
    if report in REPORTS:
        return report, None, REPORTS[report]["title"], REPORTS[report]["columns"]
    raise ValueError("unknown_report")


def _name_map(conn: Connection, workspace_id: UUID) -> Callable[[list[dict[str, Any]]], None]:
    people = {str(r["id"]): r["display_name"] for r in conn.execute(
        text("SELECT id, display_name FROM person WHERE workspace_id = :w"), {"w": workspace_id}).mappings()}
    teams = {str(r["id"]): r["name"] for r in conn.execute(
        text("SELECT id, name FROM team WHERE workspace_id = :w"), {"w": workspace_id}).mappings()}

    def enrich(rows: list[dict[str, Any]]) -> None:
        for i, r in enumerate(rows, 1):
            r.setdefault("rank", i)
            if "subject_id" in r:
                r["player"] = people.get(r["subject_id"], "Unknown")
                r["team"] = teams.get(r["subject_id"], r.get("player", "Unknown"))
            for k, out in (("batter1", "batter1_name"), ("batter2", "batter2_name"), ("person_id", "person_name")):
                if r.get(k):
                    r[out] = people.get(str(r[k]), "Unknown")
            if "members" in r and isinstance(r["members"], list):
                r["members_names"] = " & ".join(people.get(str(m), "Unknown") for m in r["members"])
    return enrich


def report_rows(conn: Connection, workspace_id: UUID, report: str, filters: dict[str, Any], **kw: Any) -> dict[str, Any]:
    base, entry, title, columns = _resolve(report)
    spec = REPORTS[base]
    f = dict(filters)
    merged = dict(entry.params) if entry else {}
    merged.update({k: v for k, v in kw.items() if v is not None})
    if entry and entry.split_default and not f.get("split"):
        f["split"] = entry.split_default
    rows = spec["fn"](conn, f, **merged)
    if entry and entry.rerank:
        metric, direction = entry.rerank
        qualified = [r for r in rows if r.get(metric) is not None and r.get("qualified", True)]
        qualified.sort(key=lambda r: r.get(metric), reverse=(direction == "desc"))
        rows = qualified[:100]
        for r in rows:
            r.pop("rank", None)
    _name_map(conn, workspace_id)(rows)
    return {"report": report, "title": title,
            "columns": [{"key": c.key, "label": c.label, "align": c.align, "decimals": c.decimals} for c in columns],
            "rows": rows}


def report_csv(conn: Connection, workspace_id: UUID, report: str, filters: dict[str, Any], **kw: Any) -> str:
    """CSV of a tabular report (same columns/rows/figures as the screen and PDF)."""
    data = report_rows(conn, workspace_id, report, filters, **kw)
    out = io.StringIO()
    w = csv.writer(out)
    cols = data["columns"]
    w.writerow([c["label"] for c in cols])
    for r in data["rows"]:
        line = []
        for c in cols:
            v = r.get(c["key"])
            if v is None:
                line.append("")
            elif c["decimals"] is not None and isinstance(v, (int, float)):
                line.append(f"{v:.{c['decimals']}f}")
            elif isinstance(v, bool):
                line.append("Yes" if v else "No")
            else:
                line.append(str(v))
        w.writerow(line)
    return out.getvalue()


def _branding(conn: Connection, settings: Settings, workspace_id: UUID) -> tuple[str, str | None, str | None]:
    ws = conn.execute(text("SELECT name FROM workspace WHERE id = :w"), {"w": workspace_id}).mappings().first()
    name = ws["name"] if ws else "OneStats"
    b = branding.get_branding(conn, workspace_id)
    logo_ref = (b or {}).get("logo_ref")
    logo_path = None
    if logo_ref:
        p = logos.logo_path(settings, workspace_id, logo_ref)
        logo_path = str(p) if p else None
    brand_hex = ((b or {}).get("colours") or {}).get("primary") if isinstance(b, dict) else None
    return name, logo_path, brand_hex


def report_pdf(conn: Connection, settings: Settings, workspace_id: UUID, report: str, filters: dict[str, Any],
               *, period: str | None = None, filter_labels: list[str] | None = None, cover: bool = False,
               **kw: Any) -> bytes:
    _base, entry, title, columns = _resolve(report)
    data = report_rows(conn, workspace_id, report, filters, **kw)
    name, logo_path, brand_hex = _branding(conn, settings, workspace_id)
    notes = [("Official statistics from approved scorecards only. Unknown values are not treated as zero; "
              "strike/economy rates use recorded balls only.")]
    if entry and entry.qualification:
        notes.append(entry.qualification)
    if entry and entry.limitations:
        notes.append(entry.limitations)
    doc = ReportDoc(title=title, workspace_name=name, period=period,
                    filters=filter_labels or [], qualification_notes=notes, cover_page=cover,
                    logo_path=logo_path, brand_hex=brand_hex,
                    sections=[Section(heading=title, columns=columns, rows=data["rows"])])
    return build_pdf(doc)


def catalogue_index_pdf(conn: Connection, settings: Settings, workspace_id: UUID) -> bytes:
    """A printable catalogue index: every report, grouped by category, with its description."""
    name, logo_path, brand_hex = _branding(conn, settings, workspace_id)
    sections = []
    for cat in CATEGORY_ORDER:
        entries = [e for e in CATALOGUE if e.category == cat]
        if not entries:
            continue
        rows = [{"name": e.name, "description": e.description} for e in entries]
        sections.append(Section(heading=cat, columns=[Column("name", "Report", width=55),
                                                      Column("description", "Description")], rows=rows))
    doc = ReportDoc(title="Report Catalogue", subtitle=f"{len(CATALOGUE)} reports", workspace_name=name,
                    orientation="portrait", cover_page=True, logo_path=logo_path, brand_hex=brand_hex,
                    qualification_notes=[("Every report uses the one deterministic statistics engine; scope "
                                          "(season, grade, competition, team, date, venue, finals) is a filter, "
                                          "not a separate report.")],
                    sections=sections)
    return build_pdf(doc)


def ladder_pdf(conn: Connection, settings: Settings, workspace_id: UUID, competition_id: UUID,
               *, season_id: UUID | None = None, grade_id: UUID | None = None) -> bytes:
    lad = competition_points.ladder(conn, workspace_id, competition_id=competition_id, season_id=season_id,
                                    grade_id=grade_id)
    teams = {str(r["id"]): r["name"] for r in conn.execute(
        text("SELECT id, name FROM team WHERE workspace_id = :w"), {"w": workspace_id}).mappings()}
    for s in lad["standings"]:
        s["team"] = teams.get(s["team_id"], "Unknown")
    name, logo_path, brand_hex = _branding(conn, settings, workspace_id)
    cols = [Column("position", "#", "right"), Column("team", "Team"), Column("played", "P", "right"),
            Column("wins", "W", "right"), Column("losses", "L", "right"), Column("draws", "D", "right"),
            Column("ties", "T", "right"), Column("no_results", "NR", "right"),
            Column("bonus", "Bonus", "right", 1), Column("points", "Points", "right", 1)]
    doc = ReportDoc(title="Competition Ladder", workspace_name=name, logo_path=logo_path, brand_hex=brand_hex,
                    qualification_notes=[lad["note"]],
                    sections=[Section(heading="Standings", columns=cols, rows=lad["standings"])])
    return build_pdf(doc)
