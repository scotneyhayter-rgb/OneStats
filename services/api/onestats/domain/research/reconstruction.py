"""Historical scorecard reconstruction (Phase 10, Stages 10.7/10.8).

Guided reconstruction of a match from one or many historical sources, keeping ONE canonical match
record. It reuses the Phase 6 scorecard model (match / innings / batting / bowling) and the Phase 7
approval workflow — there is no second scorecard engine — and records field-level provenance
(Stage 10.9) as values are entered. A match may hold only what is actually known; unknown stays
unknown. Multiple sources (editions, scorebooks, articles) contribute to the same match rather than
spawning duplicates.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import matches
from onestats.domain.research import sources


def start_reconstruction(conn: Connection, workspace_id: UUID, actor: str, *,
                         competition_id: UUID | None = None, grade_id: UUID | None = None,
                         season_id: UUID | None = None, venue_id: UUID | None = None,
                         match_date: Any | None = None, date_precision: str = "unknown",
                         match_date_end: Any | None = None, notes: str | None = None,
                         source_id: UUID | None = None, source_role: str | None = "primary") -> dict[str, Any]:
    """Create a provisional (draft) historical match and optionally attach the first source. The match
    starts with only what is known — nothing is invented to make it saveable."""
    match_id = matches.create_match(
        conn, workspace_id, actor, competition_id=competition_id, grade_id=grade_id, season_id=season_id,
        venue_id=venue_id, match_date=match_date, date_precision=date_precision, status="draft", notes=notes,
    )
    if match_date_end is not None:
        matches.update_match(conn, workspace_id, actor, match_id, match_date_end=match_date_end)
    if source_id is not None:
        sources.link_match(conn, workspace_id, actor, source_id, match_id, role=source_role)
    return matches.get_match(conn, match_id)


def attach_source(conn: Connection, workspace_id: UUID, actor: str, match_id: UUID, source_id: UUID,
                  *, role: str | None = None) -> dict[str, Any]:
    """Attach another source to an existing canonical match (an edition, scorebook or later article)."""
    return sources.link_match(conn, workspace_id, actor, source_id, match_id, role=role)


def summary(conn: Connection, workspace_id: UUID, match_id: UUID) -> dict[str, Any]:
    """A reconstruction's current state for the guided workflow: approval status, how many sources and
    provenance fields are recorded, and how many fields are still in conflict."""
    match = matches.get_match(conn, match_id)
    if match is None:
        raise ValueError("match_not_found")
    source_count = conn.execute(
        text("SELECT count(*) FROM research_source_match WHERE workspace_id = :w AND match_id = :m"),
        {"w": workspace_id, "m": match_id},
    ).scalar_one()
    field_count = conn.execute(
        text("SELECT count(DISTINCT field_path) FROM field_provenance WHERE workspace_id = :w AND match_id = :m"),
        {"w": workspace_id, "m": match_id},
    ).scalar_one()
    conflict_count = conn.execute(
        text("SELECT count(*) FROM (SELECT field_path FROM field_provenance WHERE workspace_id = :w "
             "AND match_id = :m AND status IN ('claimed','accepted') AND normalised_value IS NOT NULL "
             "GROUP BY field_path HAVING count(DISTINCT normalised_value) > 1) c"),
        {"w": workspace_id, "m": match_id},
    ).scalar_one()
    return {
        "match_id": str(match_id),
        "approval_status": match.get("approval_status"),
        "match_date": match.get("match_date").isoformat() if match.get("match_date") else None,
        "date_precision": match.get("date_precision"),
        "sources": source_count,
        "provenance_fields": field_count,
        "conflicts": conflict_count,
        "source_list": [_s(r) for r in sources.list_sources_for_match(conn, workspace_id, match_id)],
    }


def _s(d: dict[str, Any]) -> dict[str, Any]:
    return {k: (str(v) if isinstance(v, UUID) else v) for k, v in d.items()}
