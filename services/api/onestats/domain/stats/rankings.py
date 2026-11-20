"""Scoped player rankings — a transparent weighted index (Batting / Bowling / Allrounder).

The index scores every component against a FIXED benchmark constant, so a player's points are
**absolute**: they mean the same thing under any time/team filter and are comparable across windows.
Because of that, the volume component is a PER-MATCH RATE (runs/wickets per match), never a raw total —
a raw total would balloon with a wider window and break cross-window comparability.

Each component is clamped to [0, 100] and weighted; the weighted sum is 0–100. Inverse metrics
(bowling average / economy / strike rate — lower is better) score as BENCH / value. Allrounder =
batting_pts * bowling_pts / 100 (stays 0–100).

Benchmarks are FORMAT-AWARE (short formats vs longer formats). Every weight, benchmark and
qualification threshold lives in the single CONFIG block below, tunable without touching the logic.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain.stats import engine
from onestats.domain.stats.engine import _needs_match_join, _where

# ======================================================================================
# CONFIG — all tunables in one place (weights, benchmarks, qualification). Change here only.
# ======================================================================================
# Short-format match codes (match.format); everything else (incl. unset/mixed) uses the longer set.
SHORT_FORMATS: frozenset[str] = frozenset({"t20", "t20i"})

# Absolute benchmark constants per format family. A component at the benchmark scores 100 on that term.
BENCHMARKS: dict[str, dict[str, float]] = {
    "long": {   # 2-day / 50-over and other longer formats
        "bat_avg": 50.0, "rpm": 40.0, "bat_sr": 70.0, "milestone": 0.30,
        "bowl_avg": 20.0, "wpm": 2.5, "econ": 3.0, "bowl_sr": 45.0,
    },
    "short": {  # T20 / T20I
        "bat_avg": 35.0, "rpm": 30.0, "bat_sr": 140.0, "milestone": 0.25,
        "bowl_avg": 22.0, "wpm": 1.5, "econ": 7.0, "bowl_sr": 18.0,
    },
}

# Component weights (sum to 1.0 within each discipline → weighted sum stays 0–100).
WEIGHTS: dict[str, dict[str, float]] = {
    "batting": {"average": 0.40, "rpm": 0.30, "strike_rate": 0.15, "milestone": 0.15},
    "bowling": {"average": 0.30, "wpm": 0.30, "economy": 0.20, "strike_rate": 0.20},
}

# Qualification (scales with the time window). Batting qualifies at the SMALLER of a fixed innings
# floor or a share of the scoped team's matches in the window — so short windows need fewer innings.
QUALIFY: dict[str, float] = {
    "bat_min_innings": 5.0,
    "bat_team_match_pct": 0.30,
    "bowl_min_overs": 20.0,
}
# ======================================================================================

UNRANKED = "unranked — below qualification"


def _bench(fmt: str | None) -> dict[str, float]:
    return BENCHMARKS["short"] if fmt in SHORT_FORMATS else BENCHMARKS["long"]


def _clamp(x: float) -> float:
    return 0.0 if x < 0 else (100.0 if x > 100 else x)


def _direct(value: float | None, bench: float) -> float:
    """Higher-is-better component: value / bench, clamped to [0, 100]."""
    if value is None or bench <= 0:
        return 0.0
    return _clamp(value / bench * 100.0)


def _inverse(value: float | None, bench: float) -> float:
    """Lower-is-better component (bowling avg/econ/SR): bench / value, clamped. Guards divide-by-zero
    (e.g. an undefined average with 0 wickets → 0 on that term)."""
    if value is None or value <= 0:
        return 0.0
    return _clamp(bench / value * 100.0)


def _window_matches(conn: Connection, filters: dict[str, Any]) -> int:
    """Distinct matches in the filtered scope (the scoped team/club's fixtures in the window), from the
    appearance ledger — the denominator for the batting qualification share."""
    where, params = _where(filters)
    params["cal"] = "player_appearance"
    join = "JOIN match m ON m.id = c.match_id " if _needs_match_join(filters) else ""
    sql = (f"SELECT count(DISTINCT c.match_id) FROM match_stat_contribution c {join}"
           f"WHERE c.calculator = :cal AND {where}")
    return int(conn.execute(text(sql), params).scalar() or 0)


def _batting_points(r: dict[str, Any], b: dict[str, float]) -> float:
    runs, matches, inns = int(r["runs"]), int(r["matches"] or 0), int(r["innings"] or 0)
    dismissed = int(r["dismissed"])
    # standard not-out handling: average = runs / dismissals. A never-dismissed batter has no defined
    # average; rather than penalise them with 0, treat it as runs over a single dismissal (favourable).
    eff_avg = (runs / dismissed) if dismissed else (float(runs) if inns else None)
    rpm = (runs / matches) if matches else 0.0
    milestone = ((int(r["fifties"]) + 2 * int(r["hundreds"])) / inns) if inns else 0.0
    w = WEIGHTS["batting"]
    pts = (w["average"] * _direct(eff_avg, b["bat_avg"])
           + w["rpm"] * _direct(rpm, b["rpm"])
           + w["strike_rate"] * _direct(r.get("strike_rate"), b["bat_sr"])
           + w["milestone"] * _direct(milestone, b["milestone"]))
    return round(pts, 1)


def _bowling_points(r: dict[str, Any], b: dict[str, float]) -> float:
    wickets, matches = int(r["wickets"]), int(r["matches"] or 0)
    wpm = (wickets / matches) if matches else 0.0
    w = WEIGHTS["bowling"]
    pts = (w["average"] * _inverse(r.get("average"), b["bowl_avg"])
           + w["wpm"] * _direct(wpm, b["wpm"])
           + w["economy"] * _inverse(r.get("economy"), b["econ"])
           + w["strike_rate"] * _inverse(r.get("strike_rate"), b["bowl_sr"]))
    return round(pts, 1)


def _order_and_rank(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Qualified first (points desc), then unqualified (points desc). Unqualified rows carry rank=None
    (shown as "—") and a status note; qualified rows are auto-numbered by the report layer."""
    qualified = sorted((r for r in rows if r["qualified"]), key=lambda r: -r["points"])
    unranked = sorted((r for r in rows if not r["qualified"]), key=lambda r: -r["points"])
    for r in unranked:
        r["rank"] = None
        r["status"] = UNRANKED
    for r in qualified:
        r["status"] = ""
    return qualified + unranked


def player_rankings(conn: Connection, filters: dict[str, Any], *, board: str = "batting",
                    limit: int = 100) -> list[dict[str, Any]]:
    """Ranked index for one board ("batting" | "bowling" | "allrounder") over the filtered, qualified
    pool. Points are absolute (fixed benchmarks), so they are comparable across any time/team filter."""
    if board not in ("batting", "bowling", "allrounder"):
        raise ValueError("invalid_board")
    b = _bench(filters.get("format"))
    bat = {r["subject_id"]: r for r in engine.batting_leaders(conn, filters, limit=1_000_000)}
    bowl = {r["subject_id"]: r for r in engine.bowling_leaders(conn, filters, limit=1_000_000)}

    # batting qualification threshold scales with the window (smaller of the innings floor / team share)
    team_matches = _window_matches(conn, filters)
    bat_threshold = min(QUALIFY["bat_min_innings"], QUALIFY["bat_team_match_pct"] * team_matches)

    def bat_qual(r: dict[str, Any]) -> bool:
        return int(r["innings"] or 0) >= bat_threshold

    def bowl_qual(r: dict[str, Any]) -> bool:
        return float(r.get("overs") or 0) >= QUALIFY["bowl_min_overs"]

    rows: list[dict[str, Any]] = []
    if board == "batting":
        for sid, r in bat.items():
            rows.append({"subject_id": sid, "points": _batting_points(r, b), "matches": r["matches"],
                         "innings": r["innings"], "average": r.get("average"),
                         "rpm": round(int(r["runs"]) / int(r["matches"]), 2) if r["matches"] else 0.0,
                         "strike_rate": r.get("strike_rate"), "qualified": bat_qual(r)})
    elif board == "bowling":
        for sid, r in bowl.items():
            rows.append({"subject_id": sid, "points": _bowling_points(r, b), "matches": r["matches"],
                         "overs": r.get("overs"), "wickets": r["wickets"], "average": r.get("average"),
                         "economy": r.get("economy"),
                         "wpm": round(int(r["wickets"]) / int(r["matches"]), 2) if r["matches"] else 0.0,
                         "strike_rate": r.get("strike_rate"), "qualified": bowl_qual(r)})
    else:  # allrounder — candidates are players with BOTH batting and bowling in scope
        for sid in bat.keys() & bowl.keys():
            bp, wp = _batting_points(bat[sid], b), _bowling_points(bowl[sid], b)
            rows.append({"subject_id": sid, "points": round(bp * wp / 100.0, 1),
                         "batting_points": bp, "bowling_points": wp,
                         "matches": bat[sid]["matches"],
                         "qualified": bat_qual(bat[sid]) and bowl_qual(bowl[sid])})

    return _order_and_rank(rows)[:limit]
