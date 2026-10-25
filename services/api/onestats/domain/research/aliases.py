"""Historical name & alias recognition (Phase 10, Stage 10.4).

Known historical name variants used to broaden search — never to rewrite original source text. A term
is expanded to include the aliases of any entity it matches, so a search for a club finds it under its
former names, abbreviations and common transcription errors. The source's own wording is always kept
verbatim (aliases live here, not over the top of the evidence).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

ENTITY_TYPES = ("club", "competition", "grade", "team", "person", "venue", "place", "other")


def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def register_alias(conn: Connection, workspace_id: UUID, actor: str, *, entity_type: str, alias: str,
                   entity_id: UUID | None = None, alias_kind: str | None = None, language: str | None = None,
                   note: str | None = None) -> dict[str, Any]:
    if entity_type not in ENTITY_TYPES:
        raise ValueError("invalid_entity_type")
    if not (alias or "").strip():
        raise ValueError("alias_required")
    aid = conn.execute(
        text("INSERT INTO research_alias(workspace_id, entity_type, entity_id, alias, normalised, alias_kind, "
             "language, note, created_by) VALUES (:w, :et, :eid, :al, :nm, :ak, :lg, :nt, :by) "
             "ON CONFLICT ON CONSTRAINT uq_research_alias DO UPDATE SET alias = :al, alias_kind = :ak, "
             "note = :nt RETURNING id"),
        {"w": workspace_id, "et": entity_type, "eid": entity_id, "al": alias.strip(), "nm": _norm(alias),
         "ak": alias_kind, "lg": language, "nt": note, "by": actor},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "research.alias_registered", entity="research_alias",
                      entity_id=str(aid), after={"entity_type": entity_type, "alias": alias})
    r = conn.execute(text("SELECT * FROM research_alias WHERE id = :id"), {"id": aid}).mappings().first()
    return dict(r)


def list_aliases(conn: Connection, workspace_id: UUID, *, entity_type: str | None = None,
                 entity_id: UUID | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM research_alias WHERE workspace_id = :w"
    params: dict[str, Any] = {"w": workspace_id}
    if entity_type is not None:
        sql += " AND entity_type = :et"
        params["et"] = entity_type
    if entity_id is not None:
        sql += " AND entity_id = :eid"
        params["eid"] = entity_id
    sql += " ORDER BY alias"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def expand_terms(conn: Connection, workspace_id: UUID, term: str) -> list[str]:
    """Expand a search term with the aliases of every entity (or standalone alias group) it matches.
    Returns distinct terms including the original; purely additive (never alters source text)."""
    norm = _norm(term)
    if not norm:
        return []
    # entities whose aliases include a match for the term
    hits = conn.execute(
        text("SELECT DISTINCT entity_type, entity_id FROM research_alias WHERE workspace_id = :w AND normalised = :n"),
        {"w": workspace_id, "n": norm},
    ).mappings().all()
    terms = {term.strip()}
    for h in hits:
        if h["entity_id"] is not None:
            rows = conn.execute(
                text("SELECT alias FROM research_alias WHERE workspace_id = :w AND entity_type = :et "
                     "AND entity_id = :eid"),
                {"w": workspace_id, "et": h["entity_type"], "eid": h["entity_id"]},
            ).scalars().all()
        else:
            rows = conn.execute(
                text("SELECT alias FROM research_alias WHERE workspace_id = :w AND entity_type = :et "
                     "AND entity_id IS NULL AND normalised = :n"),
                {"w": workspace_id, "et": h["entity_type"], "n": norm},
            ).scalars().all()
        terms.update(rows)
    return sorted(terms)
