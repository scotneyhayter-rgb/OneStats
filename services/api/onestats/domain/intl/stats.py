"""Format-aware international statistics (Part H).

International cricket is reported BY FORMAT — a player's Test, ODI and T20I records are distinct
careers, never pooled into one line. This module is a thin, honest layer over the existing statistics
engine (:mod:`onestats.domain.stats.engine`): it runs the same approved-ledger calculators once per
format by setting the engine's ``format`` filter, so every guarantee the engine already makes is
preserved unchanged —

  * averages/strike-rates/economy are computed from summed components, never fabricated;
  * "unknown" stays distinct from zero (e.g. ``balls_incomplete``, ``runs_known_minimum``);
  * over rates use each match's OWN over length (6- vs 8-ball) from the stored balls, so historical
    8-ball-over matches are never miscomputed;
  * only approved, statistics-eligible scorecards contribute.

Nothing here writes to the database or invents a number; it only partitions and delegates. Until
matches are imported the ledger is empty, so every figure is a genuine zero/unknown, not a claim.
"""
from __future__ import annotations

from typing import Any, Callable
from uuid import UUID

from sqlalchemy.engine import Connection

from onestats.domain.stats import engine

# The three officially recognised men's international formats, in the order they are reported.
INTL_FORMATS = ("test", "odi", "t20i")

# discipline -> (leaderboard fn, per-person aggregate fn). Both take the engine's (conn, filters, ...).
_LEADERS: dict[str, Callable[..., list[dict[str, Any]]]] = {
    "batting": engine.batting_leaders,
    "bowling": engine.bowling_leaders,
    "fielding": engine.fielding_leaders,
    "participation": engine.participation_leaders,
    "captaincy": engine.captaincy_leaders,
    "team": engine.team_records,
}
DISCIPLINES = tuple(_LEADERS.keys())


def _filters(workspace_id: UUID, fmt: str | None = None,
             extra: dict[str, Any] | None = None) -> dict[str, Any]:
    f: dict[str, Any] = {"workspace_id": workspace_id}
    if fmt is not None:
        f["format"] = fmt
    if extra:
        f.update({k: v for k, v in extra.items() if v is not None})
    return f


def _person_disciplines(conn: Connection, filters: dict[str, Any], person_id: UUID) -> dict[str, Any]:
    return {
        "batting": engine.person_batting(conn, filters, person_id),
        "bowling": engine.person_bowling(conn, filters, person_id),
        "fielding": engine.person_fielding(conn, filters, person_id),
        "participation": engine.person_participation(conn, filters, person_id),
        "captaincy": engine.person_captaincy(conn, filters, person_id),
    }


def format_career(conn: Connection, workspace_id: UUID, person_id: UUID) -> dict[str, Any]:
    """A player's international career split Test / ODI / T20I, each a self-contained set of discipline
    aggregates, plus an ``all`` line.

    ``all`` is every international in this workspace (which contains only the three recognised formats),
    NOT a reinterpretation of any single format — it is the honest union, with the same unknown-aware
    flags. Format lines are never summed into the career line by the caller; each stands on its own.
    """
    formats = {
        fmt: _person_disciplines(conn, _filters(workspace_id, fmt), person_id)
        for fmt in INTL_FORMATS
    }
    combined = _person_disciplines(conn, _filters(workspace_id), person_id)
    return {"person_id": str(person_id), "formats": formats, "all": combined}


def format_leaders(conn: Connection, workspace_id: UUID, fmt: str, discipline: str, *,
                   limit: int = 100, order_by: str | None = None,
                   filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """A single-format leaderboard for one discipline, reusing the engine's calculators and all of its
    universal filters (season/team/opposition/date/venue). ``fmt`` must be one of the recognised
    international formats; ``discipline`` one of :data:`DISCIPLINES`."""
    if fmt not in INTL_FORMATS:
        raise ValueError("invalid_format")
    fn = _LEADERS.get(discipline)
    if fn is None:
        raise ValueError("invalid_discipline")
    scoped = _filters(workspace_id, fmt, filters)
    kwargs: dict[str, Any] = {"limit": limit}
    if order_by:
        kwargs["order_by"] = order_by
    return fn(conn, scoped, **kwargs)
