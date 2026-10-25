"""Research notes & evidence quality (Phase 10, Stage 10.15).

A research notebook: findings, questions, hypotheses, historical context and source limitations,
attached to a project, match and/or source. Each note carries an evidence classification
(verified / supported / oral_history / unverified / disputed) that clearly distinguishes a
researcher's interpretation from a documented fact — these are research classifications, NOT a
substitute for formal scorecard approval. Notes are retained when a match is verified.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

EVIDENCE_CLASSES = ("verified", "supported", "oral_history", "unverified", "disputed")


def create_note(conn: Connection, workspace_id: UUID, actor: str, *, body: str,
                evidence_class: str = "unverified", project_id: UUID | None = None,
                match_id: UUID | None = None, source_id: UUID | None = None) -> dict[str, Any]:
    if not (body or "").strip():
        raise ValueError("body_required")
    if evidence_class not in EVIDENCE_CLASSES:
        raise ValueError("invalid_evidence_class")
    nid = conn.execute(
        text("INSERT INTO research_note(workspace_id, project_id, match_id, source_id, body, evidence_class, "
             "author) VALUES (:w, :p, :m, :s, :b, :ec, :by) RETURNING id"),
        {"w": workspace_id, "p": project_id, "m": match_id, "s": source_id, "b": body, "ec": evidence_class,
         "by": actor},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "research.note_created", entity="research_note",
                      entity_id=str(nid), after={"evidence_class": evidence_class})
    return get_note(conn, nid)


def get_note(conn: Connection, note_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text("SELECT * FROM research_note WHERE id = :id"), {"id": note_id}).mappings().first()
    return dict(r) if r else None


def list_notes(conn: Connection, workspace_id: UUID, *, project_id: UUID | None = None,
               match_id: UUID | None = None, source_id: UUID | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM research_note WHERE workspace_id = :w"
    params: dict[str, Any] = {"w": workspace_id}
    for col, val in (("project_id", project_id), ("match_id", match_id), ("source_id", source_id)):
        if val is not None:
            sql += f" AND {col} = :{col}"
            params[col] = val
    sql += " ORDER BY created_at DESC"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]
