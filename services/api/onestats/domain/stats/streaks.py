"""Consecutive-record (streak) statistics (RMCC report catalogue §23.2, §23.8, §24.3).

Streaks are computed over the subject's **chronological** sequence of approved matches from the one
statistics ledger — team results (`team_result`) and credited-captain results (`player_captaincy`),
both of which carry the per-match `result` in their metrics. Outcome handling follows deliverable 23 §23.2:

- win / loss / draw / tie extend or break a streak per the streak type;
- abandoned / no-result are **skipped** (neither extend nor break a win/loss run);
- an **unknown** result (or a missing match date) breaks the *known* sequence and flags the subject's
  streak as a **known-minimum** — it is never assumed to be a win or a loss.

Nothing is recomputed here; this reads the same approved ledger the engine builds. Missing historical
*fixtures* cannot be detected from recorded matches alone, so a streak is asserted over recorded approved
matches and flagged known-minimum whenever the sequence contains unknowns or undated matches.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain.stats.engine import _where

# streak type -> (outcomes that extend, outcomes that are skipped/neutral). Everything else breaks the run.
_NEUTRAL = {"no_result"}
_RULES: dict[str, set[str]] = {
    "wins": {"win"},
    "losses": {"loss"},
    "unbeaten": {"win", "draw", "tie"},   # no loss
    "winless": {"loss", "draw", "tie"},   # no win
}


def _sequences(conn: Connection, calculator: str, filters: dict[str, Any]) -> dict[str, list[tuple[Any, str]]]:
    where, params = _where(filters)
    params["cal"] = calculator
    sql = ("SELECT c.subject_id AS sid, m.match_date AS d, c.metrics->>'result' AS res "
           "FROM match_stat_contribution c JOIN match m ON m.id = c.match_id "
           f"WHERE c.calculator = :cal AND {where} "
           "ORDER BY c.subject_id, m.match_date NULLS LAST")
    seqs: dict[str, list[tuple[Any, str]]] = {}
    for r in conn.execute(text(sql), params).mappings():
        seqs.setdefault(str(r["sid"]), []).append((r["d"], r["res"]))
    return seqs


def _longest(seq: list[tuple[Any, str]], extend: set[str]) -> int:
    """Longest run of ``extend`` outcomes, skipping neutral (no-result/abandoned). Unknown and any other
    outcome break the run."""
    best = cur = 0
    for _d, res in seq:
        r = res or "unknown"
        if r in _NEUTRAL:
            continue                 # skipped — neither extends nor breaks
        if r in extend:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0                  # loss/draw/tie (as applicable) or unknown breaks the run
    return best


def _known_minimum(seq: list[tuple[Any, str]]) -> bool:
    # the true streak may differ if the sequence has unknown results or undated (unorderable) matches
    return any(res is None or res == "unknown" or d is None for d, res in seq)


def _best_run(flags: list[bool]) -> tuple[int, int, int]:
    """Longest run of True in ``flags``; returns (length, start_index, end_index) (indices into flags)."""
    best = cur = best_start = best_end = cur_start = 0
    for i, ok in enumerate(flags):
        if ok:
            if cur == 0:
                cur_start = i
            cur += 1
            if cur > best:
                best, best_start, best_end = cur, cur_start, i
        else:
            cur = 0
    return best, best_start, best_end


def player_match_streaks(conn: Connection, filters: dict[str, Any], who: str, *,
                         limit: int = 100) -> list[dict[str, Any]]:
    """Longest run of consecutive matches a person **played** (who='played') or **captained**
    (who='captained'), over each team's chronological *played* fixture sequence. A match counts as a team
    fixture only if it has a recorded appearance, so a no-play forfeit (no appearances) is skipped rather
    than breaking a streak (approved forfeit policy). Recorded fixtures the person missed break the run; an
    undocumented historical gap is not assumed, and undated matches flag a known-minimum."""
    part_calc = "player_appearance" if who == "played" else "player_captaincy"
    where, params = _where(filters)
    join = "JOIN match m ON m.id = c.match_id "
    fx_rows = conn.execute(text(
        "SELECT DISTINCT c.team_id AS tid, c.match_id AS mid, m.match_date AS d, s.label AS season "
        f"FROM match_stat_contribution c {join}LEFT JOIN season s ON s.id = c.season_id "
        f"WHERE c.calculator = 'player_appearance' AND {where} ORDER BY c.team_id, m.match_date NULLS LAST"),
        params).mappings().all()
    p2 = dict(params)
    p2["pc"] = part_calc
    part_rows = conn.execute(text(
        f"SELECT c.team_id AS tid, c.match_id AS mid, coalesce(p.merged_into_id, p.id) AS pid "
        f"FROM match_stat_contribution c {join}JOIN person p ON p.id = c.subject_id "
        f"WHERE c.calculator = :pc AND {where}"), p2).mappings().all()

    fixtures: dict[Any, list[dict[str, Any]]] = {}
    for r in fx_rows:
        fixtures.setdefault(r["tid"], []).append({"mid": r["mid"], "d": r["d"], "season": r["season"]})
    participated: dict[tuple[Any, str], set] = {}
    for r in part_rows:
        participated.setdefault((r["tid"], str(r["pid"])), set()).add(r["mid"])

    people = {str(x["id"]): x["display_name"] for x in conn.execute(
        text("SELECT id, display_name FROM person WHERE workspace_id = :w"), {"w": filters["workspace_id"]}).mappings()}
    teams = {x["id"]: x["name"] for x in conn.execute(
        text("SELECT id, name FROM team WHERE workspace_id = :w"), {"w": filters["workspace_id"]}).mappings()}

    best: dict[str, dict[str, Any]] = {}
    for (tid, pid), mids in participated.items():
        fx = fixtures.get(tid, [])
        if not fx:
            continue
        flags = [f["mid"] in mids for f in fx]
        length, start_i, end_i = _best_run(flags)
        if length <= 0:
            continue
        km = any(f["d"] is None for f in fx)
        row = {"subject_id": pid, "player": people.get(pid, "Unknown"), "team_name": teams.get(tid, "Unknown"),
               "streak": length,
               "start_date": fx[start_i]["d"].isoformat() if fx[start_i]["d"] else None,
               "end_date": fx[end_i]["d"].isoformat() if fx[end_i]["d"] else None,
               "start_season": fx[start_i]["season"], "end_season": fx[end_i]["season"],
               "known_minimum": km}
        if pid not in best or length > best[pid]["streak"]:
            best[pid] = row
    rows = sorted(best.values(), key=lambda r: -r["streak"])
    return rows[:limit]


def without_duck_streaks(conn: Connection, filters: dict[str, Any], *, limit: int = 100) -> list[dict[str, Any]]:
    """Longest run of consecutive completed batting innings without a duck, per batter. A duck is a
    completed innings (dismissed) for 0; a did-not-bat is not an innings and is excluded; a not-out (any
    score) is not a duck and continues the run; an innings with unknown runs breaks the known sequence and
    flags a known-minimum (never assumed a success)."""
    # innings-level batting of approved matches, in order; needs a join to match for date + official
    sql = (
        "SELECT coalesce(p.merged_into_id, p.id) AS pid, m.match_date AS d, be.runs AS runs, be.dismissal_type AS dt "
        "FROM batting_entry be JOIN innings i ON i.id = be.innings_id JOIN match m ON m.id = i.match_id "
        "JOIN person p ON p.id = be.person_id "
        "WHERE be.person_id IS NOT NULL AND m.approval_status IN ('approved','verified_partial') "
        "AND m.include_in_statistics = true AND m.workspace_id = :w "
        "AND (be.dismissal_type IS NULL OR be.dismissal_type NOT IN ('dnb','absent')) "
        "ORDER BY coalesce(p.merged_into_id, p.id), m.match_date NULLS LAST")
    seqs: dict[str, list[dict[str, Any]]] = {}
    for r in conn.execute(text(sql), {"w": filters["workspace_id"]}).mappings():
        seqs.setdefault(str(r["pid"]), []).append({"d": r["d"], "runs": r["runs"], "dt": r["dt"]})
    people = {str(x["id"]): x["display_name"] for x in conn.execute(
        text("SELECT id, display_name FROM person WHERE workspace_id = :w"), {"w": filters["workspace_id"]}).mappings()}
    out = []
    for pid, seq in seqs.items():
        best = cur = 0
        km = any(e["d"] is None for e in seq)
        for e in seq:
            out_dismissed = e["dt"] is not None and e["dt"] not in ("not_out", "retired_not_out", "retired")
            if e["runs"] is None:
                cur = 0            # unknown runs break the known run (never assumed a non-duck)
                km = True
            elif e["runs"] == 0 and out_dismissed:
                cur = 0            # a duck breaks the run
            else:
                cur += 1           # any score, or a not-out 0, continues the run
                best = max(best, cur)
        if best > 0:
            out.append({"subject_id": pid, "player": people.get(pid, "Unknown"), "streak": best,
                        "known_minimum": km})
    out.sort(key=lambda r: -r["streak"])
    return out[:limit]


def streak_leaders(conn: Connection, calculator: str, kind: str, filters: dict[str, Any], *,
                   limit: int = 100) -> list[dict[str, Any]]:
    """Rank subjects by their longest ``kind`` streak (kind in _RULES) for the given calculator
    (``team_result`` → team streaks, ``player_captaincy`` → captaincy streaks)."""
    if kind not in _RULES:
        raise ValueError("invalid_streak_kind")
    extend = _RULES[kind]
    rows = []
    for sid, seq in _sequences(conn, calculator, filters).items():
        streak = _longest(seq, extend)
        if streak > 0:
            rows.append({"subject_id": sid, "streak": streak, "matches": len(seq),
                         "known_minimum": _known_minimum(seq)})
    rows.sort(key=lambda r: -r["streak"])
    return rows[:limit]
