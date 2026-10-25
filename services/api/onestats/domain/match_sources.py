"""Multiple historical sources per match (Phase 8, Stage 8.5 — R1).

A canonical match may be described by several sources (different exports, or different newspaper
editions). ``attach_source`` records each one against the match WITHOUT overwriting the scorecard; its
field values are kept in ``recorded_fields`` so conflicting accounts can be surfaced for administrator
review. Idempotent on (match, source_system, source_ref): re-attaching updates in place.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit


def attach_source(
    conn: Connection, workspace_id: UUID, actor: str, match_id: UUID, *,
    source_system: str, source_ref: str, recorded_fields: dict[str, Any] | None = None,
    edition: str | None = None, filename: str | None = None, sha256: str | None = None,
) -> dict[str, Any]:
    """Record a source for a match (idempotent). Returns the row id and whether it was newly created.
    Never alters the match itself — this is additional evidence, not an overwrite."""
    fields_json = json.dumps(recorded_fields, default=str) if recorded_fields is not None else None
    existing = conn.execute(
        text("SELECT id FROM match_source WHERE match_id = :m AND source_system = :ss AND source_ref = :sr"),
        {"m": match_id, "ss": source_system, "sr": source_ref},
    ).scalar_one_or_none()
    if existing is not None:
        conn.execute(
            text("UPDATE match_source SET recorded_fields = CAST(:f AS jsonb), edition = COALESCE(:ed, edition), "
                 "source_filename = COALESCE(:fn, source_filename), source_sha256 = COALESCE(:sha, source_sha256), "
                 "updated_at = now() WHERE id = :id"),
            {"f": fields_json, "ed": edition, "fn": filename, "sha": sha256, "id": existing},
        )
        return {"match_source_id": str(existing), "created": False}
    new_id = conn.execute(
        text("INSERT INTO match_source(workspace_id, match_id, source_system, source_ref, source_filename, "
             "source_sha256, edition, recorded_fields, created_by) "
             "VALUES (:w, :m, :ss, :sr, :fn, :sha, :ed, CAST(:f AS jsonb), :by) RETURNING id"),
        {"w": workspace_id, "m": match_id, "ss": source_system, "sr": source_ref, "fn": filename,
         "sha": sha256, "ed": edition, "f": fields_json, "by": actor},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "match.attach_source", entity="match", entity_id=str(match_id),
                      after={"source_system": source_system, "source_ref": source_ref, "edition": edition})
    return {"match_source_id": str(new_id), "created": True}


def list_match_sources(conn: Connection, match_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("SELECT id, source_system, source_ref, edition, source_filename, source_sha256, "
             "recorded_fields, created_at FROM match_source WHERE match_id = :m "
             "ORDER BY created_at, source_system, source_ref"),
        {"m": match_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def source_conflicts(conn: Connection, match_id: UUID) -> list[dict[str, Any]]:
    """Fields on which the match's sources disagree — surfaced for administrator review, never auto
    -resolved. A field appears only when two or more sources record different non-null values for it."""
    sources = list_match_sources(conn, match_id)
    by_field: dict[str, list[dict[str, Any]]] = {}
    for s in sources:
        for field, value in (s.get("recorded_fields") or {}).items():
            if value is None:
                continue
            by_field.setdefault(field, []).append(
                {"source_system": s["source_system"], "source_ref": s["source_ref"],
                 "edition": s["edition"], "value": value})
    conflicts: list[dict[str, Any]] = []
    for field, entries in by_field.items():
        distinct = {str(e["value"]) for e in entries}
        if len(distinct) > 1:
            conflicts.append({"field": field, "values": entries})
    return conflicts
