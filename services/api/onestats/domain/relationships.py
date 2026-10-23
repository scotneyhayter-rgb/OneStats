"""Organisation lifecycle & historical relationships (Phase 4, Stage 5).

Time-bounded relationships between **distinct** organisations — mergers/amalgamations, renames,
affiliations, association transfers, predecessor/successor links. These document how clubs evolve
without ever merging identities or reassigning historical records: a historical amalgamation is
NOT an administrative duplicate-record merge (that remains the separate Stage 1 operation).

Integrity rules enforced here:

* **No self-links** (DB CHECK) and **no lineage cycles**: a lineage edge (merger/amalgamation/
  rename/predecessor/successor) is rejected if the target can already reach the source through
  lineage edges.
* **No overlapping exclusive affiliations**: a new ``association_transfer`` for a club is rejected
  if its period overlaps an existing one (a club plays in one association at a time). Sequential
  transfers and non-exclusive ``affiliation`` links are allowed.
* **Reversible & correctable**: relationships can be voided (preserving the original row) and
  corrected; nothing is hard-deleted by default.
* **Unknown stays unknown**: null ``valid_from``/``valid_to`` are explicit, never invented.

Workspace-scoped (RLS); governed by ``organisation.manage``; all changes audited.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

_TYPES = (
    "merger", "amalgamation", "rename", "affiliation",
    "association_transfer", "predecessor", "successor", "other",
)
# Types that express an identity lineage and so must stay acyclic.
_LINEAGE_TYPES = ("merger", "amalgamation", "rename", "predecessor", "successor")
_EXCLUSIVE_TYPES = ("association_transfer",)
_MAX_WALK = 256

_COLS = (
    "id, workspace_id, from_org_id, to_org_id, rel_type, valid_from, valid_to, notes, "
    "evidence, source_system, source_ref, is_void, voided_at, voided_by, created_at"
)


def _org_exists(conn: Connection, org_id: UUID) -> bool:
    return conn.execute(text("SELECT 1 FROM organisation WHERE id = :o"), {"o": org_id}).first() is not None


def _overlaps(a_from, a_to, b_from, b_to) -> bool:
    """Do two (nullable) date ranges intersect? Null = open-ended (-inf / +inf)."""
    # a starts after b ends, or b starts after a ends -> no overlap; otherwise they intersect.
    a_after_b = a_from is not None and b_to is not None and a_from > b_to
    b_after_a = b_from is not None and a_to is not None and b_from > a_to
    return not (a_after_b or b_after_a)


def _would_cycle(conn: Connection, from_org: UUID, to_org: UUID) -> bool:
    """Would a lineage edge from_org → to_org create a cycle? True if to_org can already reach
    from_org by following active lineage edges (to_org →* from_org)."""
    placeholders = ",".join(f"'{t}'" for t in _LINEAGE_TYPES)
    seen: set[UUID] = set()
    frontier = [to_org]
    for _ in range(_MAX_WALK):
        if not frontier:
            return False
        node = frontier.pop()
        if node == from_org:
            return True
        if node in seen:
            continue
        seen.add(node)
        nxt = conn.execute(
            text(
                f"SELECT to_org_id FROM organisation_relationship "
                f"WHERE from_org_id = :n AND is_void = false AND rel_type IN ({placeholders})"
            ),
            {"n": node},
        ).scalars().all()
        frontier.extend(nxt)
    raise ValueError("relationship_graph_too_deep")


def get_relationship(conn: Connection, rel_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(
        text(f"SELECT {_COLS} FROM organisation_relationship WHERE id = :id"), {"id": rel_id}
    ).mappings().first()
    return dict(r) if r else None


def create_relationship(
    conn: Connection, workspace_id: UUID, actor: str,
    *, from_org_id: UUID, to_org_id: UUID, rel_type: str,
    valid_from: Any | None = None, valid_to: Any | None = None,
    notes: str | None = None, evidence: str | None = None,
    source_system: str | None = None, source_ref: str | None = None,
) -> UUID:
    if rel_type not in _TYPES:
        raise ValueError("invalid_rel_type")
    if from_org_id == to_org_id:
        raise ValueError("self_relationship")
    if not _org_exists(conn, from_org_id) or not _org_exists(conn, to_org_id):
        raise ValueError("organisation_not_found")
    if valid_from is not None and valid_to is not None and valid_to < valid_from:
        raise ValueError("invalid_date_range")

    if rel_type in _LINEAGE_TYPES and _would_cycle(conn, from_org_id, to_org_id):
        raise ValueError("relationship_cycle")

    if rel_type in _EXCLUSIVE_TYPES:
        # Reject an overlapping exclusive affiliation for the same club.
        existing = conn.execute(
            text(
                "SELECT valid_from, valid_to FROM organisation_relationship "
                "WHERE from_org_id = :f AND rel_type = :t AND is_void = false"
            ),
            {"f": from_org_id, "t": rel_type},
        ).mappings().all()
        for row in existing:
            if _overlaps(valid_from, valid_to, row["valid_from"], row["valid_to"]):
                raise ValueError("overlapping_affiliation")

    rel_id = conn.execute(
        text(
            "INSERT INTO organisation_relationship"
            "(workspace_id, from_org_id, to_org_id, rel_type, valid_from, valid_to, notes, "
            " evidence, source_system, source_ref) "
            "VALUES (:w, :f, :t, :rt, :vf, :vt, :notes, :ev, :ss, :sr) RETURNING id"
        ),
        {"w": workspace_id, "f": from_org_id, "t": to_org_id, "rt": rel_type,
         "vf": valid_from, "vt": valid_to, "notes": notes, "ev": evidence,
         "ss": source_system, "sr": source_ref},
    ).scalar_one()
    audit.write_audit(
        conn, workspace_id, actor, "organisation_relationship.create",
        entity="organisation_relationship", entity_id=str(rel_id),
        after={"from_org_id": str(from_org_id), "to_org_id": str(to_org_id), "rel_type": rel_type,
               "valid_from": str(valid_from) if valid_from else None},
    )
    return rel_id


def correct_relationship(
    conn: Connection, workspace_id: UUID, actor: str, rel_id: UUID,
    *, valid_from: Any | None = None, valid_to: Any | None = None,
    notes: str | None = None, evidence: str | None = None, set_dates: bool = False,
) -> dict[str, Any]:
    """Correct a relationship's dates/notes/evidence (original row preserved via audit before/
    after). ``set_dates=True`` applies ``valid_from``/``valid_to`` exactly (including clearing to
    NULL); otherwise only non-null values are applied."""
    before = get_relationship(conn, rel_id)
    if before is None:
        raise ValueError("relationship_not_found")
    sets, params = [], {"id": rel_id}
    if set_dates:
        if valid_from is not None and valid_to is not None and valid_to < valid_from:
            raise ValueError("invalid_date_range")
        sets += ["valid_from = :vf", "valid_to = :vt"]
        params["vf"] = valid_from
        params["vt"] = valid_to
    if notes is not None:
        sets.append("notes = :notes")
        params["notes"] = notes
    if evidence is not None:
        sets.append("evidence = :ev")
        params["ev"] = evidence
    if sets:
        conn.execute(text(f"UPDATE organisation_relationship SET {', '.join(sets)} WHERE id = :id"), params)
    after = get_relationship(conn, rel_id)
    audit.write_audit(
        conn, workspace_id, actor, "organisation_relationship.correct",
        entity="organisation_relationship", entity_id=str(rel_id), before=before, after=after,
    )
    return after


def void_relationship(conn: Connection, workspace_id: UUID, actor: str, rel_id: UUID) -> dict[str, Any]:
    """Reverse (void) a relationship, preserving the row. Idempotent-safe: voiding an already
    void row raises."""
    before = get_relationship(conn, rel_id)
    if before is None:
        raise ValueError("relationship_not_found")
    if before["is_void"]:
        raise ValueError("already_void")
    conn.execute(
        text("UPDATE organisation_relationship SET is_void = true, voided_at = now(), voided_by = :a WHERE id = :id"),
        {"a": actor, "id": rel_id},
    )
    audit.write_audit(
        conn, workspace_id, actor, "organisation_relationship.void",
        entity="organisation_relationship", entity_id=str(rel_id), before=before,
    )
    return get_relationship(conn, rel_id)


def restore_relationship(conn: Connection, workspace_id: UUID, actor: str, rel_id: UUID) -> dict[str, Any]:
    """Un-void a previously voided relationship (reversal is itself reversible)."""
    before = get_relationship(conn, rel_id)
    if before is None:
        raise ValueError("relationship_not_found")
    if not before["is_void"]:
        raise ValueError("not_void")
    # Re-apply the exclusivity/cycle guards in case the graph changed while it was void.
    if before["rel_type"] in _LINEAGE_TYPES and _would_cycle(conn, before["from_org_id"], before["to_org_id"]):
        raise ValueError("relationship_cycle")
    conn.execute(
        text("UPDATE organisation_relationship SET is_void = false, voided_at = NULL, voided_by = NULL WHERE id = :id"),
        {"id": rel_id},
    )
    audit.write_audit(
        conn, workspace_id, actor, "organisation_relationship.restore",
        entity="organisation_relationship", entity_id=str(rel_id), after={"restored": True},
    )
    return get_relationship(conn, rel_id)


def list_relationships(
    conn: Connection, org_id: UUID, *, include_void: bool = False, direction: str = "both",
) -> list[dict[str, Any]]:
    """Relationships touching ``org_id``. ``direction`` = from | to | both."""
    clauses = []
    if direction == "from":
        clauses.append("from_org_id = :o")
    elif direction == "to":
        clauses.append("to_org_id = :o")
    else:
        clauses.append("(from_org_id = :o OR to_org_id = :o)")
    if not include_void:
        clauses.append("is_void = false")
    sql = f"SELECT {_COLS} FROM organisation_relationship WHERE " + " AND ".join(clauses)
    sql += " ORDER BY valid_from NULLS FIRST, created_at"
    return [dict(r) for r in conn.execute(text(sql), {"o": org_id}).mappings().all()]


def resolve_affiliation(conn: Connection, org_id: UUID, on_date: Any) -> dict[str, Any] | None:
    """The association a club was affiliated with on ``on_date`` (by documented association_transfer
    whose period covers the date). Returns None when undocumented — never guessed."""
    row = conn.execute(
        text(
            "SELECT id, to_org_id, valid_from, valid_to FROM organisation_relationship "
            "WHERE from_org_id = :o AND rel_type = 'association_transfer' AND is_void = false "
            "AND (valid_from IS NULL OR valid_from <= :d) AND (valid_to IS NULL OR valid_to >= :d) "
            "ORDER BY valid_from DESC NULLS LAST LIMIT 1"
        ),
        {"o": org_id, "d": on_date},
    ).mappings().first()
    return dict(row) if row else None


def organisation_timeline(conn: Connection, org_id: UUID) -> dict[str, Any]:
    """Assemble timeline data for an organisation: formation/identity, name changes, and all
    (non-void) relationships, with uncertainty preserved (null dates surface as unknown).
    Compatible with the planned Historical Research Timeline."""
    org = conn.execute(
        text("SELECT id, name, kind, is_historical, status, source_system, source_ref, created_at "
             "FROM organisation WHERE id = :o"),
        {"o": org_id},
    ).mappings().first()
    if org is None:
        raise ValueError("organisation_not_found")
    names = conn.execute(
        text("SELECT name, valid_from, valid_to, note FROM organisation_name_history "
             "WHERE organisation_id = :o ORDER BY valid_from NULLS FIRST, created_at"),
        {"o": org_id},
    ).mappings().all()
    rels = list_relationships(conn, org_id, include_void=False, direction="both")
    events: list[dict[str, Any]] = []
    for n in names:
        events.append({
            "kind": "name", "name": n["name"],
            "valid_from": n["valid_from"], "valid_to": n["valid_to"], "note": n["note"],
            "uncertain": n["valid_from"] is None,
        })
    for r in rels:
        events.append({
            "kind": "relationship", "rel_type": r["rel_type"],
            "from_org_id": str(r["from_org_id"]), "to_org_id": str(r["to_org_id"]),
            "valid_from": r["valid_from"], "valid_to": r["valid_to"],
            "evidence": r["evidence"], "note": r["notes"],
            "uncertain": r["valid_from"] is None,
        })
    # Order by known start date; unknown-dated events sort first (explicitly uncertain).
    events.sort(key=lambda e: (e["valid_from"] is not None, e["valid_from"] or ""))
    return {"organisation": dict(org), "events": events}
