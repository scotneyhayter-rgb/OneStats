"""Automatic season assignment (Phase 7, Stage 7.4).

Determines a match's season from its date using the competition's configured ``season_model`` — or
an existing season whose date range already covers the date — and never guesses: when the rule is
``unknown``/``custom`` with no covering season, the season is left unresolved and flagged. A manual
season choice is preserved and never overwritten. Idempotent; uses the existing season architecture
(``season`` rows with label + start/end dates under a competition).

Supported models: Australian summer (two-year span, e.g. 2019/20), calendar year, UK summer (single
calendar-year summer), custom (defined season date ranges only), and unknown.
"""
from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit, competitions, matches

# cutoff month for the Australian summer: months >= this start the N/N+1 season (so Oct 2019 -> 2019/20)
_AU_CUTOFF_MONTH = 7


def _coerce_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def season_for_model(model: str, d: date) -> tuple[str, date, date] | None:
    """(label, start_date, end_date) implied by a season model for a date, or None when the model
    does not support an automatic determination (``custom``/``unknown``)."""
    if model == "au_summer":
        start_year = d.year if d.month >= _AU_CUTOFF_MONTH else d.year - 1
        return f"{start_year}/{(start_year + 1) % 100:02d}", date(start_year, 7, 1), date(start_year + 1, 6, 30)
    if model == "calendar":
        return str(d.year), date(d.year, 1, 1), date(d.year, 12, 31)
    if model == "uk_summer":
        return str(d.year), date(d.year, 4, 1), date(d.year, 9, 30)
    return None


def resolve_season(
    conn: Connection, workspace_id: UUID, actor: str, competition_id: UUID, match_date: Any, *, create: bool = True,
) -> UUID | None:
    """The season id for a match date: an existing season whose date range covers it, else the one
    implied by the competition's ``season_model`` (found by label or created). None when unresolved."""
    d = _coerce_date(match_date)
    if d is None:
        return None
    # 1) an existing season whose known date range already covers this date (custom/imported seasons)
    covering = conn.execute(
        text("SELECT id FROM season WHERE competition_id = :c AND start_date IS NOT NULL "
             "AND end_date IS NOT NULL AND start_date <= :d AND end_date >= :d ORDER BY start_date LIMIT 1"),
        {"c": competition_id, "d": d},
    ).scalar_one_or_none()
    if covering is not None:
        return covering
    # 2) compute from the competition's season model
    model = conn.execute(text("SELECT season_model FROM competition WHERE id = :c"),
                         {"c": competition_id}).scalar_one_or_none() or "unknown"
    implied = season_for_model(model, d)
    if implied is None:
        return None
    label, sd, ed = implied
    existing = conn.execute(
        text("SELECT id FROM season WHERE competition_id = :c AND label = :l LIMIT 1"),
        {"c": competition_id, "l": label},
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    if not create:
        return None
    return competitions.create_season(conn, workspace_id, actor, competition_id,
                                      label=label, start_date=sd, end_date=ed)


def auto_assign_season(conn: Connection, workspace_id: UUID, actor: str, match_id: UUID) -> dict[str, Any]:
    """Assign the match's season automatically, unless it was set manually (which is preserved).
    Idempotent; non-destructive; leaves the season unresolved rather than guessing."""
    match = matches.get_match(conn, match_id)
    if match is None:
        raise ValueError("match_not_found")
    if match.get("season_source") == "manual":
        return {"applied": False, "reason": "preserved manual season"}
    comp_id, m_date = match.get("competition_id"), match.get("match_date")
    if comp_id is None or m_date is None:
        return {"applied": False, "reason": "no competition or match date"}
    season_id = resolve_season(conn, workspace_id, actor, comp_id, m_date)
    if season_id is None:
        return {"applied": False, "reason": "season rules do not determine a season"}
    if match.get("season_id") == season_id and match.get("season_source") == "calculated":
        return {"applied": False, "reason": "already assigned"}
    conn.execute(text("UPDATE match SET season_id = :s, season_source = 'calculated', updated_at = now() WHERE id = :m"),
                 {"s": season_id, "m": match_id})
    audit.write_audit(conn, workspace_id, actor, "match.season_auto", entity="match", entity_id=str(match_id),
                      after={"season_id": str(season_id)})
    return {"applied": True, "season_id": str(season_id)}


def reassign_competition_matches(
    conn: Connection, workspace_id: UUID, actor: str, competition_id: UUID,
) -> dict[str, Any]:
    """Re-run automatic season assignment for every match in a competition — used when the
    competition's season rule changes, so existing (including imported) matches are back-filled
    rather than left unresolved until each is re-saved.

    Non-destructive and idempotent: a manually chosen season is preserved, a match with no date is
    left unresolved, and nothing is guessed. Returns how many matches were assigned a season."""
    ids = conn.execute(
        text("SELECT id FROM match WHERE competition_id = :c AND match_date IS NOT NULL "
             "AND coalesce(season_source, 'unknown') <> 'manual'"),
        {"c": competition_id},
    ).scalars().all()
    assigned = 0
    for mid in ids:
        if auto_assign_season(conn, workspace_id, actor, mid).get("applied"):
            assigned += 1
    return {"matches": len(ids), "assigned": assigned}


def season_warnings(conn: Connection, match_id: UUID) -> list[str]:
    """Advisory: a match with a date and competition but no resolved season (rule unknown)."""
    match = matches.get_match(conn, match_id)
    if match is None or match.get("season_id") is not None:
        return []
    if match.get("competition_id") is not None and match.get("match_date") is not None:
        return ["season_unresolved: the competition's season rules do not determine a season — set it manually or configure the competition"]
    return []
