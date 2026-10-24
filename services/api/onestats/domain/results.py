"""Automatic match results & winning margins (Phase 7, Stage 7.3).

Computes a match result from the scorecard **where the evidence is sufficient** and never guesses:

* Limited-overs (two innings total): win by runs (defending side, 2nd innings complete), win by
  wickets (chasing side passed the target), or a tie (equal totals, 2nd innings complete).
* Multi-innings or single-innings matches are returned as ``requires_review`` — not guessed.
* A partial scorecard (unknown totals, or a 2nd innings that is neither complete nor past the
  target) yields ``insufficient`` — no result is invented.

Provenance is respected: ``auto_apply_result`` only sets/updates a ``calculated`` (or previously
``unknown``) result. An official ``recorded`` result (e.g. an imported CricketStatz code) or a
``manual`` administrator override is **preserved**; where it disagrees with the calculated result,
``result_warnings`` surfaces an advisory conflict rather than overwriting it. Idempotent — repeated
recalculation produces no duplicate records (it updates the single match row in place).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import batting, matches
from onestats.domain import innings as innings_domain

MAX_WICKETS = 10  # standard; special formats may differ (future playing-conditions work)
_COMPLETE_STATUSES = ("completed", "closed", "declared", "forfeited")


def _innings_figures(conn: Connection, inn: dict[str, Any]) -> tuple[int | None, int | None]:
    """Best-known (total, wickets) for an innings: official values where set, else derived from the
    batting card plus known extras. Unknown stays None — never treated as zero."""
    card = batting.batting_card(conn, inn["id"])
    if inn.get("official_total") is not None:
        total = inn["official_total"]
    elif card.get("runs_total") is not None:
        extras = sum(v for v in (inn.get("byes"), inn.get("legbyes"), inn.get("wides"),
                                 inn.get("noballs"), inn.get("penalty")) if v is not None)
        total = card["runs_total"] + extras
    else:
        total = None
    wickets = inn["official_wickets"] if inn.get("official_wickets") is not None else card.get("wickets")
    return total, wickets


def _home_away(conn: Connection, match_id: UUID) -> tuple[UUID | None, UUID | None]:
    rows = conn.execute(
        text("SELECT team_id, is_home FROM match_team WHERE match_id = :m"), {"m": match_id}
    ).mappings().all()
    home = next((r["team_id"] for r in rows if r["is_home"]), None)
    away = next((r["team_id"] for r in rows if not r["is_home"]), None)
    return home, away


def compute_result(conn: Connection, match_id: UUID) -> dict[str, Any]:
    """Return the result implied by the scorecard. ``status`` is 'sufficient' (with result_type /
    won_by_team_id / margins / basis), 'insufficient' or 'requires_review' (both with a reason)."""
    if matches.get_match(conn, match_id) is None:
        raise ValueError("match_not_found")
    inns = innings_domain.list_innings(conn, match_id)
    if not inns:
        return {"status": "insufficient", "reason": "no innings recorded"}
    if len(inns) != 2:
        return {"status": "requires_review",
                "reason": "multi-innings or single-innings result is not auto-calculated"}

    home, away = _home_away(conn, match_id)
    first, second = inns[0], inns[1]
    t1, _w1 = _innings_figures(conn, first)
    t2, w2 = _innings_figures(conn, second)
    if t1 is None or t2 is None:
        return {"status": "insufficient", "reason": "one or both innings totals are unknown"}

    bat1, bat2 = first.get("batting_team_id"), second.get("batting_team_id")
    second_complete = second.get("status") in _COMPLETE_STATUSES or (w2 is not None and w2 >= MAX_WICKETS)

    def _as(team: UUID | None, runs: int | None, wkts: int | None, basis: str) -> dict[str, Any]:
        rtype = "home_win" if team is not None and team == home else "away_win" if team is not None and team == away else None
        return {"status": "sufficient", "result_type": rtype, "won_by_team_id": team,
                "margin_runs": runs, "margin_wickets": wkts, "basis": basis}

    if t2 > t1:   # side batting second passed the target -> win by wickets
        return _as(bat2, None, (MAX_WICKETS - w2) if w2 is not None else None,
                   f"chased {t1 + 1} ({t2}/{w2 if w2 is not None else '?'})")
    if t1 > t2:   # side batting first defended -> win by runs, only if the 2nd innings is complete
        if not second_complete:
            return {"status": "insufficient",
                    "reason": "side batting first leads but the second innings is not complete"}
        return _as(bat1, t1 - t2, None, f"defended {t1} vs {t2} all out")
    # equal totals
    if second_complete:
        return {"status": "sufficient", "result_type": "tie", "won_by_team_id": None,
                "margin_runs": None, "margin_wickets": None, "basis": f"scores level at {t1}"}
    return {"status": "insufficient", "reason": "scores level but the second innings is not complete"}


def _is_authoritative(match: dict[str, Any]) -> bool:
    """A result that must be preserved, never auto-overwritten: an administrator override
    (``manual``), an official/imported result (``recorded``), or any result that carries a preserved
    raw source code (an imported CricketStatz result) even if its provenance flag was not backfilled."""
    if match.get("result_source") in ("recorded", "manual"):
        return True
    return bool(match.get("result_raw")) and match.get("result_type") not in (None, "unknown")


def auto_apply_result(conn: Connection, workspace_id: UUID, actor: str, match_id: UUID) -> dict[str, Any]:
    """Recalculate and store the result ONLY when it is not authoritative (i.e. currently calculated
    or genuinely unknown). A recorded/manual/imported result is preserved untouched. Idempotent."""
    match = matches.get_match(conn, match_id)
    if match is None:
        raise ValueError("match_not_found")
    if _is_authoritative(match):
        return {"applied": False, "reason": "preserved recorded/manual result"}
    computed = compute_result(conn, match_id)
    if computed["status"] != "sufficient" or computed.get("result_type") is None:
        return {"applied": False, "reason": computed.get("reason", computed["status"])}
    matches.set_result(
        conn, workspace_id, actor, match_id, result_type=computed["result_type"],
        won_by_team_id=computed["won_by_team_id"], margin_runs=computed.get("margin_runs"),
        margin_wickets=computed.get("margin_wickets"), result_source="calculated",
    )
    return {"applied": True, "result_type": computed["result_type"], "basis": computed["basis"]}


def recalc_for_innings(conn: Connection, workspace_id: UUID, actor: str, innings_id: UUID) -> None:
    """Recalculate the parent match's result after an innings' scorecard changes. Non-blocking: a
    match that cannot be resolved or computed is simply left unchanged (the edit still saves)."""
    try:
        mid = conn.execute(text("SELECT match_id FROM innings WHERE id = :i"), {"i": innings_id}).scalar_one_or_none()
        if mid is not None:
            auto_apply_result(conn, workspace_id, actor, mid)
    except ValueError:
        pass


def result_warnings(conn: Connection, match_id: UUID) -> list[str]:
    """Advisory: when a recorded/manual result disagrees with the calculated one, flag it for review
    (never overwrites). Non-blocking; returns an empty list when there is nothing to report."""
    match = matches.get_match(conn, match_id)
    if match is None or not _is_authoritative(match):
        return []
    computed = compute_result(conn, match_id)
    if computed["status"] != "sufficient":
        return []
    same = (computed.get("result_type") == match.get("result_type")
            and computed.get("margin_runs") == match.get("margin_runs")
            and computed.get("margin_wickets") == match.get("margin_wickets"))
    if same:
        return []
    return ["result_conflict: recorded result differs from the result calculated from the scorecard — please review"]
