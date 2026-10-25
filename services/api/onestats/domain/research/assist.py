"""Research assistance (Phase 10, Stage 10.16).

Evidence-grounded suggestions only — never invented facts. Every suggestion is derived from data already
in the workspace (sources, provenance, match fields) and remains a suggestion until a researcher acts on
it. This is NOT the conversational Ask OneStats assistant (Phase 14); it exposes reusable research
signals that later phases can consume.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain.research import provenance

# Key match-level facts a reconstruction usually needs; used only to flag what has no evidence yet.
KEY_FIELDS = ("match.date", "match.result", "match.venue", "match.competition", "match.teams")


def suggestions_for_match(conn: Connection, workspace_id: UUID, match_id: UUID,
                          *, window_days: int = 14) -> dict[str, Any]:
    """Suggestions for one reconstruction: unresolved conflicts, key facts still lacking any source,
    sources published near the match date that are not yet linked, and duplicate linked sources. All
    grounded in existing data; nothing is asserted as fact."""
    conflicts = provenance.field_conflicts(conn, workspace_id, match_id)

    claimed_fields = {
        r["field_path"] for r in conn.execute(
            text("SELECT DISTINCT field_path FROM field_provenance WHERE workspace_id = :w AND match_id = :m"),
            {"w": workspace_id, "m": match_id}).mappings().all()
    }
    missing_key_fields = [f for f in KEY_FIELDS if f not in claimed_fields]

    # sources published within +/- window_days of the match date that are not yet attached to it
    related = conn.execute(
        text("SELECT rs.id, rs.title, rs.publication, rs.publication_date FROM research_source rs "
             "JOIN match m ON m.id = :m AND m.workspace_id = :w "
             "WHERE rs.workspace_id = :w AND rs.publication_date IS NOT NULL AND m.match_date IS NOT NULL "
             "AND abs(rs.publication_date - m.match_date) <= :win "
             "AND rs.id NOT IN (SELECT source_id FROM research_source_match WHERE match_id = :m) "
             "ORDER BY abs(rs.publication_date - m.match_date) LIMIT 10"),
        {"w": workspace_id, "m": match_id, "win": window_days},
    ).mappings().all()

    # linked sources that share identical file content (likely duplicate material)
    dup_rows = conn.execute(
        text("SELECT rs.file_sha256, count(*) AS n FROM research_source_match l "
             "JOIN research_source rs ON rs.id = l.source_id "
             "WHERE l.workspace_id = :w AND l.match_id = :m AND rs.file_sha256 IS NOT NULL "
             "GROUP BY rs.file_sha256 HAVING count(*) > 1"),
        {"w": workspace_id, "m": match_id},
    ).mappings().all()

    return {
        "conflicts": [{"field_path": c["field_path"], "claim_count": len(c["claims"])} for c in conflicts],
        "missing_key_fields": missing_key_fields,
        "suggested_related_sources": [
            {"source_id": str(r["id"]), "title": r["title"], "publication": r["publication"],
             "publication_date": r["publication_date"].isoformat() if r["publication_date"] else None}
            for r in related],
        "duplicate_source_groups": [{"file_sha256": r["file_sha256"], "count": r["n"]} for r in dup_rows],
        "disclaimer": "Suggestions are evidence-derived hints, not facts. A researcher must review and decide.",
    }
