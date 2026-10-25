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
