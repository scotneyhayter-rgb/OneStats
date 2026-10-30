"""Organisations & historical identity (Phase 4, Stage 1).

Clubs, associations, international teams and historical clubs, each workspace-scoped under
FORCE RLS. The model keeps *identity* deliberately conservative:

* **Period-correct names** — an organisation carries a current ``name`` plus an append-only
  ``organisation_name_history`` of past names with optional effective dates.
* **Provenance** — external ``organisation_source_identity`` rows (source_system + source_ref)
  record where a record came from and make re-import idempotent, without ever asserting that
  two sources are the same organisation.
* **Evidence-based duplicate review** — :func:`find_duplicate_candidates` only *suggests*
  possible duplicates (shared source identity, or an identical normalised name). It NEVER
  merges anything, and matching names/initials alone is treated as a weak hint, not proof.
* **Administrator-approved, reversible merge** — :func:`merge_organisations` is an explicit
  action that points a record at a canonical one via ``merged_into_id`` and logs an
  ``organisation_merge`` row; :func:`undo_merge` reverses it. No child rows are rewritten or
  deleted, so a merge never destroys the merged record's own history.
* **"Definitely Different" assertions** — :func:`assert_distinct` records that a pair are
  known-separate (e.g. Rhymney CC vs Moyston CC vs Rhymney/Moyston CC); an asserted pair can
  never be merged.

Every mutation is audited. Callers must have set the workspace context (``onestats.workspace_id``)
so RLS scopes all reads and writes to the one workspace.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

_KINDS = ("club", "association", "intl_team", "historical_club")
_ORG_COLS = (
    "id, workspace_id, name, short_name, kind, is_historical, status, notes, "
    "merged_into_id, source_system, source_ref, logo_ref, created_at"
)
_MAX_CHAIN = 16  # cycle guard when resolving a canonical organisation


def _normalise_name(name: str) -> str:
    """Loose key for *suggesting* name matches. Advisory only — never used to auto-merge."""
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _ordered_pair(a: UUID, b: UUID) -> tuple[UUID, UUID]:
    """Canonical ordering for a distinct-assertion pair so (a,b) and (b,a) are one row."""
    return (a, b) if str(a) <= str(b) else (b, a)


# --------------------------------------------------------------------------- reads


def get_organisation(conn: Connection, org_id: UUID) -> dict[str, Any] | None:
    row = conn.execute(
        text(f"SELECT {_ORG_COLS} FROM organisation WHERE id = :id"), {"id": org_id}
    ).mappings().first()
    return dict(row) if row else None


def set_logo(conn: Connection, org_id: UUID, logo_ref: str | None) -> None:
    """Point an organisation at a stored logo (or clear it). The image bytes are managed by
    ``domain.logos`` in workspace-isolated media; only the filename reference lives on the row."""
    conn.execute(
        text("UPDATE organisation SET logo_ref = :ref WHERE id = :id"),
        {"ref": logo_ref, "id": org_id},
    )


def list_organisations(
    conn: Connection, *, include_merged: bool = False, kind: str | None = None
) -> list[dict[str, Any]]:
    sql = f"SELECT {_ORG_COLS} FROM organisation"
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if not include_merged:
        clauses.append("merged_into_id IS NULL")
    if kind is not None:
        clauses.append("kind = :kind")
        params["kind"] = kind
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY name"
    rows = conn.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


def list_name_history(conn: Connection, org_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT id, name, valid_from, valid_to, note, created_at "
            "FROM organisation_name_history WHERE organisation_id = :o "
            "ORDER BY valid_from NULLS FIRST, created_at"
        ),
        {"o": org_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def list_source_identities(conn: Connection, org_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT id, source_system, source_ref, source_display_name, created_at "
            "FROM organisation_source_identity WHERE organisation_id = :o "
            "ORDER BY source_system, source_ref"
        ),
        {"o": org_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def name_as_of(conn: Connection, org_id: UUID, on_date: Any) -> str | None:
    """Period-correct name: the historical name whose effective range covers ``on_date``.

    A row matches when ``valid_from`` is null or on/before the date AND ``valid_to`` is null or
    on/after it. When several match (overlapping/open ranges) the most specific start wins. When
    none match (the date predates all recorded names) the earliest recorded name is returned, so
    a best-effort answer is given without inventing one. Returns None if no history exists.
    """
    row = conn.execute(
        text(
            "SELECT name FROM organisation_name_history "
            "WHERE organisation_id = :o "
            "AND (valid_from IS NULL OR valid_from <= :d) "
            "AND (valid_to IS NULL OR valid_to >= :d) "
            "ORDER BY valid_from DESC NULLS LAST, created_at DESC LIMIT 1"
        ),
        {"o": org_id, "d": on_date},
    ).scalar_one_or_none()
    if row is not None:
        return row
    return conn.execute(
        text(
            "SELECT name FROM organisation_name_history WHERE organisation_id = :o "
            "ORDER BY valid_from NULLS FIRST, created_at LIMIT 1"
        ),
        {"o": org_id},
    ).scalar_one_or_none()


def resolve_canonical(conn: Connection, org_id: UUID) -> UUID:
    """Follow the ``merged_into_id`` chain to the surviving canonical organisation."""
    current = org_id
    for _ in range(_MAX_CHAIN):
        nxt = conn.execute(
            text("SELECT merged_into_id FROM organisation WHERE id = :id"), {"id": current}
        ).scalar_one_or_none()
        if nxt is None:
            return current
        current = nxt
    raise ValueError("merge_chain_too_deep")


# --------------------------------------------------------------------------- writes


def create_organisation(
    conn: Connection,
    workspace_id: UUID,
    actor: str,
    *,
    name: str,
    kind: str = "club",
    short_name: str | None = None,
    is_historical: bool = False,
    notes: str | None = None,
    source_system: str | None = None,
    source_ref: str | None = None,
) -> UUID:
    name = (name or "").strip()
    if not name:
        raise ValueError("missing_name")
    if kind not in _KINDS:
        raise ValueError("invalid_kind")
    org_id = conn.execute(
        text(
            "INSERT INTO organisation"
            "(workspace_id, name, short_name, kind, is_historical, notes, source_system, source_ref) "
            "VALUES (:w, :n, :sn, :k, :h, :notes, :ss, :sr) RETURNING id"
        ),
        {
            "w": workspace_id, "n": name, "sn": short_name, "k": kind,
            "h": is_historical, "notes": notes, "ss": source_system, "sr": source_ref,
        },
    ).scalar_one()
    # Seed the name history with the founding/current name.
    conn.execute(
        text(
            "INSERT INTO organisation_name_history(workspace_id, organisation_id, name, note) "
            "VALUES (:w, :o, :n, 'initial name')"
        ),
        {"w": workspace_id, "o": org_id, "n": name},
    )
    # Record provenance when supplied (idempotent on the source reference).
    if source_system and source_ref:
        add_source_identity(
            conn, workspace_id, actor, org_id,
            source_system=source_system, source_ref=source_ref, source_display_name=name,
            _audit=False,
        )
    audit.write_audit(
        conn, workspace_id, actor, "organisation.create", entity="organisation",
        entity_id=str(org_id), after={"name": name, "kind": kind, "is_historical": is_historical},
    )
    return org_id


def update_organisation(
    conn: Connection,
    workspace_id: UUID,
    actor: str,
    org_id: UUID,
    *,
    name: str | None = None,
    short_name: str | None = None,
    kind: str | None = None,
    status: str | None = None,
    is_historical: bool | None = None,
    notes: str | None = None,
    name_change_note: str | None = None,
) -> dict[str, Any]:
    before = get_organisation(conn, org_id)
    if before is None:
        raise ValueError("organisation_not_found")
    if kind is not None and kind not in _KINDS:
        raise ValueError("invalid_kind")
    new_name = name.strip() if name is not None else None
    if name is not None and not new_name:
        raise ValueError("missing_name")
    conn.execute(
        text(
            "UPDATE organisation SET "
            "name = coalesce(:n, name), short_name = coalesce(:sn, short_name), "
            "kind = coalesce(:k, kind), status = coalesce(:st, status), "
            "is_historical = coalesce(:h, is_historical), notes = coalesce(:notes, notes) "
            "WHERE id = :id"
        ),
        {
            "n": new_name, "sn": short_name, "k": kind, "st": status,
            "h": is_historical, "notes": notes, "id": org_id,
        },
    )
    # A name change is preserved in the append-only history (period-correct naming).
    if new_name and new_name != before["name"]:
        conn.execute(
            text(
                "INSERT INTO organisation_name_history(workspace_id, organisation_id, name, note) "
                "VALUES (:w, :o, :n, :note)"
            ),
            {"w": workspace_id, "o": org_id, "n": new_name, "note": name_change_note or "renamed"},
        )
    after = get_organisation(conn, org_id)
    audit.write_audit(
        conn, workspace_id, actor, "organisation.update", entity="organisation",
        entity_id=str(org_id), before=before, after=after,
    )
    return after


def add_name_history(
    conn: Connection,
    workspace_id: UUID,
    actor: str,
    org_id: UUID,
    *,
    name: str,
    valid_from: Any | None = None,
    valid_to: Any | None = None,
    note: str | None = None,
) -> UUID:
    name = (name or "").strip()
    if not name:
        raise ValueError("missing_name")
    if get_organisation(conn, org_id) is None:
        raise ValueError("organisation_not_found")
    hist_id = conn.execute(
        text(
            "INSERT INTO organisation_name_history"
            "(workspace_id, organisation_id, name, valid_from, valid_to, note) "
            "VALUES (:w, :o, :n, :vf, :vt, :note) RETURNING id"
        ),
        {"w": workspace_id, "o": org_id, "n": name, "vf": valid_from, "vt": valid_to, "note": note},
    ).scalar_one()
    audit.write_audit(
        conn, workspace_id, actor, "organisation.name_history.add", entity="organisation",
        entity_id=str(org_id), after={"name": name, "valid_from": str(valid_from) if valid_from else None},
    )
    return hist_id


def add_source_identity(
    conn: Connection,
    workspace_id: UUID,
    actor: str,
    org_id: UUID,
    *,
    source_system: str,
    source_ref: str,
    source_display_name: str | None = None,
    _audit: bool = True,
) -> dict[str, Any]:
    """Attach external provenance. Idempotent on (workspace, source_system, source_ref): if the
    reference already exists it is returned unchanged (supports re-import without duplication).
    Never infers that two records are the same organisation from the source alone."""
    if not source_system or not source_ref:
        raise ValueError("missing_source_ref")
    existing = conn.execute(
        text(
            "SELECT id, organisation_id, source_system, source_ref, source_display_name "
            "FROM organisation_source_identity "
            "WHERE source_system = :ss AND source_ref = :sr"
        ),
        {"ss": source_system, "sr": source_ref},
    ).mappings().first()
    if existing is not None:
        return dict(existing) | {"created": False}
    row = conn.execute(
        text(
            "INSERT INTO organisation_source_identity"
            "(workspace_id, organisation_id, source_system, source_ref, source_display_name) "
            "VALUES (:w, :o, :ss, :sr, :dn) "
            "RETURNING id, organisation_id, source_system, source_ref, source_display_name"
        ),
        {"w": workspace_id, "o": org_id, "ss": source_system, "sr": source_ref, "dn": source_display_name},
    ).mappings().one()
    if _audit:
        audit.write_audit(
            conn, workspace_id, actor, "organisation.source_identity.add", entity="organisation",
            entity_id=str(org_id), after={"source_system": source_system, "source_ref": source_ref},
        )
    return dict(row) | {"created": True}


# ----------------------------------------------------------------- distinct assertions


def are_asserted_distinct(conn: Connection, org_a: UUID, org_b: UUID) -> bool:
    a, b = _ordered_pair(org_a, org_b)
    return conn.execute(
        text(
            "SELECT 1 FROM organisation_distinct_assertion "
            "WHERE organisation_a_id = :a AND organisation_b_id = :b"
        ),
        {"a": a, "b": b},
    ).first() is not None


def assert_distinct(
    conn: Connection, workspace_id: UUID, actor: str, org_a: UUID, org_b: UUID, *, reason: str | None = None
) -> UUID:
    """Record that two organisations are known to be *different* (prevents any future merge)."""
    if org_a == org_b:
        raise ValueError("same_organisation")
    for oid in (org_a, org_b):
        if get_organisation(conn, oid) is None:
            raise ValueError("organisation_not_found")
    a, b = _ordered_pair(org_a, org_b)
    existing = conn.execute(
        text(
            "SELECT id FROM organisation_distinct_assertion "
            "WHERE organisation_a_id = :a AND organisation_b_id = :b"
        ),
        {"a": a, "b": b},
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    assertion_id = conn.execute(
        text(
            "INSERT INTO organisation_distinct_assertion"
            "(workspace_id, organisation_a_id, organisation_b_id, actor, reason) "
            "VALUES (:w, :a, :b, :actor, :reason) RETURNING id"
        ),
        {"w": workspace_id, "a": a, "b": b, "actor": actor, "reason": reason},
    ).scalar_one()
    audit.write_audit(
        conn, workspace_id, actor, "organisation.assert_distinct", entity="organisation",
        entity_id=str(a), after={"organisation_a_id": str(a), "organisation_b_id": str(b), "reason": reason},
    )
    return assertion_id


# ----------------------------------------------------------------- duplicate review


def find_duplicate_candidates(conn: Connection, org_id: UUID) -> list[dict[str, Any]]:
    """Suggest *possible* duplicates of ``org_id`` for human review.

    Evidence surfaced (strongest first): a shared external source identity, then an identical
    normalised name. Candidates already merged, or asserted distinct from this organisation, are
    excluded. This function only advises — it performs no merge, and a name match on its own is
    explicitly NOT treated as proof of sameness.
    """
    org = get_organisation(conn, org_id)
    if org is None:
        raise ValueError("organisation_not_found")

    candidates: dict[UUID, dict[str, Any]] = {}

    # Evidence 1: another organisation carrying one of this org's source identities.
    shared = conn.execute(
        text(
            "SELECT DISTINCT other.organisation_id AS oid "
            "FROM organisation_source_identity mine "
            "JOIN organisation_source_identity other "
            "  ON other.source_system = mine.source_system AND other.source_ref = mine.source_ref "
            "WHERE mine.organisation_id = :o AND other.organisation_id <> :o"
        ),
        {"o": org_id},
    ).scalars().all()
    for oid in shared:
        candidates.setdefault(oid, {"organisation_id": oid, "evidence": []})["evidence"].append(
            "shared_source_identity"
        )

    # Evidence 2 (weak): identical normalised current name.
    key = _normalise_name(org["name"])
    same_name = conn.execute(
        text(
            "SELECT id FROM organisation "
            "WHERE id <> :o AND merged_into_id IS NULL "
            "AND regexp_replace(lower(btrim(name)), '\\s+', ' ', 'g') = :k"
        ),
        {"o": org_id, "k": key},
    ).scalars().all()
    for oid in same_name:
        candidates.setdefault(oid, {"organisation_id": oid, "evidence": []})["evidence"].append(
            "same_normalised_name"
        )

    results: list[dict[str, Any]] = []
    for oid, info in candidates.items():
        if are_asserted_distinct(conn, org_id, oid):
            continue  # a human already said these are different — do not re-suggest
        cand = get_organisation(conn, oid)
        if cand is None or cand["merged_into_id"] is not None:
            continue
        results.append({
            "organisation_id": oid,
            "name": cand["name"],
            "evidence": info["evidence"],
            "confidence": "strong" if "shared_source_identity" in info["evidence"] else "weak",
        })
    # Strong (source-backed) evidence first, then by name for stability.
    results.sort(key=lambda r: (r["confidence"] != "strong", r["name"]))
    return results


# ----------------------------------------------------------------- merge / undo


def merge_organisations(
    conn: Connection,
    workspace_id: UUID,
    actor: str,
    canonical_id: UUID,
    merged_id: UUID,
    *,
    reason: str | None = None,
) -> dict[str, Any]:
    """Merge ``merged_id`` into ``canonical_id`` (explicit, administrator-approved, reversible).

    Guards: the pair must differ, both must exist, neither may already be merged, and the pair
    must not be asserted distinct. Nothing is deleted — the merged record keeps its own name
    history and source identities and is simply marked as pointing at the canonical record, so
    the operation can be fully undone.
    """
    if canonical_id == merged_id:
        raise ValueError("cannot_merge_same")
    canonical = get_organisation(conn, canonical_id)
    merged = get_organisation(conn, merged_id)
    if canonical is None or merged is None:
        raise ValueError("organisation_not_found")
    if canonical["merged_into_id"] is not None:
        raise ValueError("canonical_already_merged")
    if merged["merged_into_id"] is not None:
        raise ValueError("already_merged")
    if are_asserted_distinct(conn, canonical_id, merged_id):
        raise ValueError("asserted_distinct")

    conn.execute(
        text("UPDATE organisation SET merged_into_id = :c, status = 'merged' WHERE id = :m"),
        {"c": canonical_id, "m": merged_id},
    )
    merge_id = conn.execute(
        text(
            "INSERT INTO organisation_merge"
            "(workspace_id, canonical_organisation_id, merged_organisation_id, actor, reason) "
            "VALUES (:w, :c, :m, :actor, :reason) RETURNING id"
        ),
        {"w": workspace_id, "c": canonical_id, "m": merged_id, "actor": actor, "reason": reason},
    ).scalar_one()
    audit.write_audit(
        conn, workspace_id, actor, "organisation.merge", entity="organisation",
        entity_id=str(merged_id),
        after={"canonical_organisation_id": str(canonical_id), "merged_organisation_id": str(merged_id),
               "reason": reason},
    )
    return {"merge_id": merge_id, "canonical_organisation_id": canonical_id,
            "merged_organisation_id": merged_id}


def undo_merge(conn: Connection, workspace_id: UUID, actor: str, merge_id: UUID) -> dict[str, Any]:
    """Reverse a merge: the merged organisation is reinstated as an independent record."""
    row = conn.execute(
        text(
            "SELECT id, canonical_organisation_id, merged_organisation_id, is_undone "
            "FROM organisation_merge WHERE id = :id"
        ),
        {"id": merge_id},
    ).mappings().first()
    if row is None:
        raise ValueError("merge_not_found")
    if row["is_undone"]:
        raise ValueError("already_undone")
    merged_id = row["merged_organisation_id"]
    conn.execute(
        text("UPDATE organisation SET merged_into_id = NULL, status = 'active' WHERE id = :m"),
        {"m": merged_id},
    )
    conn.execute(
        text(
            "UPDATE organisation_merge SET is_undone = true, undone_at = now(), undone_by = :actor "
            "WHERE id = :id"
        ),
        {"actor": actor, "id": merge_id},
    )
    audit.write_audit(
        conn, workspace_id, actor, "organisation.merge.undo", entity="organisation",
        entity_id=str(merged_id), after={"merge_id": str(merge_id)},
    )
    return {"merge_id": merge_id, "merged_organisation_id": merged_id, "undone": True}
