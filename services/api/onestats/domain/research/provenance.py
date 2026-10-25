"""Field-level historical provenance (Phase 10, Stage 10.9/10.10).

Each material fact of a reconstructed match (date, result, a batter's score, bowling figures, …) is
traced to the source(s) that support it. Multiple sources may confirm or disagree about a value; both
are kept. Accepting one claim supersedes the competing claims for that field but never deletes them —
the complete claim history and the reason for each decision are preserved.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

STATUS = ("claimed", "accepted", "rejected", "superseded")


def record_claim(conn: Connection, workspace_id: UUID, actor: str, *, match_id: UUID, field_path: str,
                 source_id: UUID | None, claimed_value: str | None, normalised_value: str | None = None,
                 confidence: float | None = None, researcher: str | None = None) -> dict[str, Any]:
    """Record (or update, per source) a source's claim about a field. Unknown stays NULL — never 0."""
    if not (field_path or "").strip():
        raise ValueError("field_path_required")
    pid = conn.execute(
        text("INSERT INTO field_provenance(workspace_id, match_id, field_path, source_id, claimed_value, "
             "normalised_value, confidence, researcher, status) "
             "VALUES (:w, :m, :fp, :s, :cv, :nv, :conf, :r, 'claimed') "
             "ON CONFLICT ON CONSTRAINT uq_field_provenance DO UPDATE SET "
             "claimed_value = :cv, normalised_value = :nv, confidence = :conf, researcher = :r, "
             "status = CASE WHEN field_provenance.status = 'rejected' THEN 'claimed' ELSE field_provenance.status END, "
             "updated_at = now() RETURNING id"),
        {"w": workspace_id, "m": match_id, "fp": field_path.strip(), "s": source_id, "cv": claimed_value,
         "nv": normalised_value, "conf": confidence, "r": researcher},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "research.claim_recorded", entity="field_provenance",
                      entity_id=str(pid), after={"field_path": field_path, "normalised_value": normalised_value})
    return get_claim(conn, pid)


def get_claim(conn: Connection, claim_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text("SELECT * FROM field_provenance WHERE id = :id"), {"id": claim_id}).mappings().first()
    return dict(r) if r else None


def list_for_match(conn: Connection, workspace_id: UUID, match_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("SELECT * FROM field_provenance WHERE workspace_id = :w AND match_id = :m "
             "ORDER BY field_path, created_at"),
        {"w": workspace_id, "m": match_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def list_for_field(conn: Connection, workspace_id: UUID, match_id: UUID, field_path: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("SELECT * FROM field_provenance WHERE workspace_id = :w AND match_id = :m AND field_path = :fp "
             "ORDER BY created_at"),
        {"w": workspace_id, "m": match_id, "fp": field_path},
    ).mappings().all()
    return [dict(r) for r in rows]


def field_conflicts(conn: Connection, workspace_id: UUID, match_id: UUID) -> list[dict[str, Any]]:
    """Fields where the live claims (claimed or accepted — not rejected or superseded) disagree: more
    than one distinct normalised value. Each entry lists every claim so sources compare side by side."""
    paths = conn.execute(
        text("SELECT field_path FROM field_provenance "
             "WHERE workspace_id = :w AND match_id = :m AND status IN ('claimed','accepted') "
             "AND normalised_value IS NOT NULL "
             "GROUP BY field_path HAVING count(DISTINCT normalised_value) > 1 ORDER BY field_path"),
        {"w": workspace_id, "m": match_id},
    ).scalars().all()
    return [{"field_path": p, "claims": list_for_field(conn, workspace_id, match_id, p)} for p in paths]


def accept_claim(conn: Connection, workspace_id: UUID, actor: str, claim_id: UUID,
                 *, note: str | None = None) -> dict[str, Any]:
    """Accept one claim for its field; competing live claims for the same field are superseded (kept,
    not deleted) and point to the accepted claim. Rejected claims stay rejected (retained)."""
    claim = get_claim(conn, claim_id)
    if claim is None:
        raise ValueError("claim_not_found")
    conn.execute(
        text("UPDATE field_provenance SET status = 'superseded', superseded_by = :acc, updated_at = now() "
             "WHERE workspace_id = :w AND match_id = :m AND field_path = :fp AND id <> :acc AND status <> 'rejected'"),
        {"acc": claim_id, "w": workspace_id, "m": claim["match_id"], "fp": claim["field_path"]},
    )
    conn.execute(
        text("UPDATE field_provenance SET status = 'accepted', superseded_by = NULL, decision_note = :n, "
             "updated_at = now() WHERE id = :id"),
        {"n": note, "id": claim_id},
    )
    audit.write_audit(conn, workspace_id, actor, "research.claim_accepted", entity="field_provenance",
                      entity_id=str(claim_id), after={"field_path": claim["field_path"]})
    return get_claim(conn, claim_id)


def reject_claim(conn: Connection, workspace_id: UUID, actor: str, claim_id: UUID,
                 *, note: str | None = None) -> dict[str, Any]:
    """Reject a claim, retaining it and the reason (rejected claims are never discarded)."""
    if get_claim(conn, claim_id) is None:
        raise ValueError("claim_not_found")
    conn.execute(
        text("UPDATE field_provenance SET status = 'rejected', superseded_by = NULL, decision_note = :n, "
             "updated_at = now() WHERE id = :id"),
        {"n": note, "id": claim_id},
    )
    audit.write_audit(conn, workspace_id, actor, "research.claim_rejected", entity="field_provenance",
                      entity_id=str(claim_id), after={"note": note})
    return get_claim(conn, claim_id)
