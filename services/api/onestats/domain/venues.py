"""Venues (grounds) & their historical identity (Phase 4, Stage 2).

A venue is a standalone, workspace-scoped ground reusable by many clubs, teams and competitions.
It carries the same conservative identity machinery as organisations (Stage 1): period-correct
name history, external source identities (provenance), evidence-based duplicate *suggestions*,
administrator-approved reversible merges, and explicit "definitely different" assertions.

Location and coordinates are optional and never invented — a missing or ``"?"`` value is stored
as NULL. Renaming a ground preserves its old name in history, so historical match attribution is
never lost. Every mutation is audited. Callers must have set the workspace context so RLS scopes
all reads and writes to the one workspace.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

_COLS = (
    "id, workspace_id, name, short_name, status, address, locality, region, country, postcode, "
    "latitude, longitude, notes, merged_into_id, source_system, source_ref, created_at"
)
_MAX_CHAIN = 16


def _clean(value: str | None) -> str | None:
    """Normalise an optional free-text field: blanks and the source sentinel ``"?"`` → NULL
    (unknown stays unknown; nothing is invented)."""
    if value is None:
        return None
    v = value.strip()
    return None if v in ("", "?") else v


def _normalise_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _ordered_pair(a: UUID, b: UUID) -> tuple[UUID, UUID]:
    return (a, b) if str(a) <= str(b) else (b, a)


# --------------------------------------------------------------------------- reads


def get_venue(conn: Connection, venue_id: UUID) -> dict[str, Any] | None:
    row = conn.execute(
        text(f"SELECT {_COLS} FROM venue WHERE id = :id"), {"id": venue_id}
    ).mappings().first()
    return dict(row) if row else None


def list_venues(
    conn: Connection, *, include_merged: bool = False, search: str | None = None
) -> list[dict[str, Any]]:
    sql = f"SELECT {_COLS} FROM venue"
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if not include_merged:
        clauses.append("merged_into_id IS NULL")
    if search:
        clauses.append("(name ILIKE :q OR locality ILIKE :q OR region ILIKE :q)")
        params["q"] = f"%{search}%"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY name"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def list_name_history(conn: Connection, venue_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT id, name, valid_from, valid_to, note, created_at "
            "FROM venue_name_history WHERE venue_id = :o "
            "ORDER BY valid_from NULLS FIRST, created_at"
        ),
        {"o": venue_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def list_source_identities(conn: Connection, venue_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT id, source_system, source_ref, source_display_name, created_at "
            "FROM venue_source_identity WHERE venue_id = :o ORDER BY source_system, source_ref"
        ),
        {"o": venue_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def name_as_of(conn: Connection, venue_id: UUID, on_date: Any) -> str | None:
    row = conn.execute(
        text(
            "SELECT name FROM venue_name_history WHERE venue_id = :o "
            "AND (valid_from IS NULL OR valid_from <= :d) "
            "AND (valid_to IS NULL OR valid_to >= :d) "
            "ORDER BY valid_from DESC NULLS LAST, created_at DESC LIMIT 1"
        ),
        {"o": venue_id, "d": on_date},
    ).scalar_one_or_none()
    if row is not None:
        return row
    return conn.execute(
        text(
            "SELECT name FROM venue_name_history WHERE venue_id = :o "
            "ORDER BY valid_from NULLS FIRST, created_at LIMIT 1"
        ),
        {"o": venue_id},
    ).scalar_one_or_none()


def resolve_canonical(conn: Connection, venue_id: UUID) -> UUID:
    current = venue_id
    for _ in range(_MAX_CHAIN):
        nxt = conn.execute(
            text("SELECT merged_into_id FROM venue WHERE id = :id"), {"id": current}
        ).scalar_one_or_none()
        if nxt is None:
            return current
        current = nxt
    raise ValueError("merge_chain_too_deep")


# --------------------------------------------------------------------------- writes


def create_venue(
    conn: Connection,
    workspace_id: UUID,
    actor: str,
    *,
    name: str,
    short_name: str | None = None,
    address: str | None = None,
    locality: str | None = None,
    region: str | None = None,
    country: str | None = None,
    postcode: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    notes: str | None = None,
    source_system: str | None = None,
    source_ref: str | None = None,
) -> UUID:
    name = (name or "").strip()
    if not name:
        raise ValueError("missing_name")
    venue_id = conn.execute(
        text(
            "INSERT INTO venue"
            "(workspace_id, name, short_name, address, locality, region, country, postcode, "
            " latitude, longitude, notes, source_system, source_ref) "
            "VALUES (:w, :n, :sn, :addr, :loc, :reg, :cty, :pc, :lat, :lon, :notes, :ss, :sr) "
            "RETURNING id"
        ),
        {
            "w": workspace_id, "n": name, "sn": _clean(short_name),
            "addr": _clean(address), "loc": _clean(locality), "reg": _clean(region),
            "cty": _clean(country), "pc": _clean(postcode),
            "lat": latitude, "lon": longitude, "notes": _clean(notes),
            "ss": source_system, "sr": source_ref,
        },
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO venue_name_history(workspace_id, venue_id, name, note) "
            "VALUES (:w, :o, :n, 'initial name')"
        ),
        {"w": workspace_id, "o": venue_id, "n": name},
    )
    if source_system and source_ref:
        add_source_identity(
            conn, workspace_id, actor, venue_id,
            source_system=source_system, source_ref=source_ref, source_display_name=name,
            _audit=False,
        )
    audit.write_audit(
        conn, workspace_id, actor, "venue.create", entity="venue",
        entity_id=str(venue_id), after={"name": name, "locality": _clean(locality)},
    )
    return venue_id


def update_venue(
    conn: Connection, workspace_id: UUID, actor: str, venue_id: UUID,
    *, name_change_note: str | None = None, **fields: Any,
) -> dict[str, Any]:
    before = get_venue(conn, venue_id)
    if before is None:
        raise ValueError("venue_not_found")
    allowed = {
        "name", "short_name", "status", "address", "locality", "region", "country",
        "postcode", "latitude", "longitude", "notes",
    }
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    new_name = None
    if "name" in updates:
        new_name = str(updates["name"]).strip()
        if not new_name:
            raise ValueError("missing_name")
        updates["name"] = new_name
    for text_field in ("short_name", "address", "locality", "region", "country", "postcode", "notes"):
        if text_field in updates:
            updates[text_field] = _clean(str(updates[text_field]))
    if updates:
        sets = ", ".join(f"{k} = :{k}" for k in updates)
        conn.execute(text(f"UPDATE venue SET {sets} WHERE id = :id"), {**updates, "id": venue_id})
    if new_name and new_name != before["name"]:
        conn.execute(
            text(
                "INSERT INTO venue_name_history(workspace_id, venue_id, name, note) "
                "VALUES (:w, :o, :n, :note)"
            ),
            {"w": workspace_id, "o": venue_id, "n": new_name, "note": name_change_note or "renamed"},
        )
    after = get_venue(conn, venue_id)
    audit.write_audit(
        conn, workspace_id, actor, "venue.update", entity="venue",
        entity_id=str(venue_id), before=before, after=after,
    )
    return after


def add_name_history(
    conn: Connection, workspace_id: UUID, actor: str, venue_id: UUID,
    *, name: str, valid_from: Any | None = None, valid_to: Any | None = None, note: str | None = None,
) -> UUID:
    name = (name or "").strip()
    if not name:
        raise ValueError("missing_name")
    if get_venue(conn, venue_id) is None:
        raise ValueError("venue_not_found")
    hist_id = conn.execute(
        text(
            "INSERT INTO venue_name_history(workspace_id, venue_id, name, valid_from, valid_to, note) "
            "VALUES (:w, :o, :n, :vf, :vt, :note) RETURNING id"
        ),
        {"w": workspace_id, "o": venue_id, "n": name, "vf": valid_from, "vt": valid_to, "note": note},
    ).scalar_one()
    audit.write_audit(
        conn, workspace_id, actor, "venue.name_history.add", entity="venue",
        entity_id=str(venue_id), after={"name": name},
    )
    return hist_id


def add_source_identity(
    conn: Connection, workspace_id: UUID, actor: str, venue_id: UUID,
    *, source_system: str, source_ref: str, source_display_name: str | None = None, _audit: bool = True,
) -> dict[str, Any]:
    if not source_system or not source_ref:
        raise ValueError("missing_source_ref")
    existing = conn.execute(
        text(
            "SELECT id, venue_id, source_system, source_ref, source_display_name "
            "FROM venue_source_identity WHERE source_system = :ss AND source_ref = :sr"
        ),
        {"ss": source_system, "sr": source_ref},
    ).mappings().first()
    if existing is not None:
        return dict(existing) | {"created": False}
    row = conn.execute(
        text(
            "INSERT INTO venue_source_identity"
            "(workspace_id, venue_id, source_system, source_ref, source_display_name) "
            "VALUES (:w, :o, :ss, :sr, :dn) "
            "RETURNING id, venue_id, source_system, source_ref, source_display_name"
        ),
        {"w": workspace_id, "o": venue_id, "ss": source_system, "sr": source_ref, "dn": source_display_name},
    ).mappings().one()
    if _audit:
        audit.write_audit(
            conn, workspace_id, actor, "venue.source_identity.add", entity="venue",
            entity_id=str(venue_id), after={"source_system": source_system, "source_ref": source_ref},
        )
    return dict(row) | {"created": True}


# ----------------------------------------------------------------- distinct assertions


def are_asserted_distinct(conn: Connection, a: UUID, b: UUID) -> bool:
    x, y = _ordered_pair(a, b)
    return conn.execute(
        text(
            "SELECT 1 FROM venue_distinct_assertion "
            "WHERE venue_a_id = :a AND venue_b_id = :b"
        ),
        {"a": x, "b": y},
    ).first() is not None


def assert_distinct(
    conn: Connection, workspace_id: UUID, actor: str, a: UUID, b: UUID, *, reason: str | None = None
) -> UUID:
    if a == b:
        raise ValueError("same_venue")
    for vid in (a, b):
        if get_venue(conn, vid) is None:
            raise ValueError("venue_not_found")
    x, y = _ordered_pair(a, b)
    existing = conn.execute(
        text("SELECT id FROM venue_distinct_assertion WHERE venue_a_id = :a AND venue_b_id = :b"),
        {"a": x, "b": y},
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    assertion_id = conn.execute(
        text(
            "INSERT INTO venue_distinct_assertion(workspace_id, venue_a_id, venue_b_id, actor, reason) "
            "VALUES (:w, :a, :b, :actor, :reason) RETURNING id"
        ),
        {"w": workspace_id, "a": x, "b": y, "actor": actor, "reason": reason},
    ).scalar_one()
    audit.write_audit(
        conn, workspace_id, actor, "venue.assert_distinct", entity="venue",
        entity_id=str(x), after={"venue_a_id": str(x), "venue_b_id": str(y), "reason": reason},
    )
    return assertion_id


# ----------------------------------------------------------------- duplicate review


def find_duplicate_candidates(conn: Connection, venue_id: UUID) -> list[dict[str, Any]]:
    """Suggest possible duplicate grounds for human review (shared source identity = strong;
    identical normalised name = weak). Never merges; a name match alone is not proof."""
    venue = get_venue(conn, venue_id)
    if venue is None:
        raise ValueError("venue_not_found")
    candidates: dict[UUID, dict[str, Any]] = {}

    shared = conn.execute(
        text(
            "SELECT DISTINCT other.venue_id AS oid FROM venue_source_identity mine "
            "JOIN venue_source_identity other "
            "  ON other.source_system = mine.source_system AND other.source_ref = mine.source_ref "
            "WHERE mine.venue_id = :o AND other.venue_id <> :o"
        ),
        {"o": venue_id},
    ).scalars().all()
    for oid in shared:
        candidates.setdefault(oid, {"evidence": []})["evidence"].append("shared_source_identity")

    key = _normalise_name(venue["name"])
    same_name = conn.execute(
        text(
            "SELECT id FROM venue WHERE id <> :o AND merged_into_id IS NULL "
            "AND regexp_replace(lower(btrim(name)), '\\s+', ' ', 'g') = :k"
        ),
        {"o": venue_id, "k": key},
    ).scalars().all()
    for oid in same_name:
        candidates.setdefault(oid, {"evidence": []})["evidence"].append("same_normalised_name")

    results: list[dict[str, Any]] = []
    for oid, info in candidates.items():
        if are_asserted_distinct(conn, venue_id, oid):
            continue
        cand = get_venue(conn, oid)
        if cand is None or cand["merged_into_id"] is not None:
            continue
        results.append({
            "venue_id": oid, "name": cand["name"], "evidence": info["evidence"],
            "confidence": "strong" if "shared_source_identity" in info["evidence"] else "weak",
        })
    results.sort(key=lambda r: (r["confidence"] != "strong", r["name"]))
    return results


# ----------------------------------------------------------------- merge / undo


def merge_venues(
    conn: Connection, workspace_id: UUID, actor: str, canonical_id: UUID, merged_id: UUID,
    *, reason: str | None = None,
) -> dict[str, Any]:
    if canonical_id == merged_id:
        raise ValueError("cannot_merge_same")
    canonical = get_venue(conn, canonical_id)
    merged = get_venue(conn, merged_id)
    if canonical is None or merged is None:
        raise ValueError("venue_not_found")
    if canonical["merged_into_id"] is not None:
        raise ValueError("canonical_already_merged")
    if merged["merged_into_id"] is not None:
        raise ValueError("already_merged")
    if are_asserted_distinct(conn, canonical_id, merged_id):
        raise ValueError("asserted_distinct")
    conn.execute(
        text("UPDATE venue SET merged_into_id = :c, status = 'merged' WHERE id = :m"),
        {"c": canonical_id, "m": merged_id},
    )
    merge_id = conn.execute(
        text(
            "INSERT INTO venue_merge(workspace_id, canonical_venue_id, merged_venue_id, actor, reason) "
            "VALUES (:w, :c, :m, :actor, :reason) RETURNING id"
        ),
        {"w": workspace_id, "c": canonical_id, "m": merged_id, "actor": actor, "reason": reason},
    ).scalar_one()
    audit.write_audit(
        conn, workspace_id, actor, "venue.merge", entity="venue", entity_id=str(merged_id),
        after={"canonical_venue_id": str(canonical_id), "merged_venue_id": str(merged_id), "reason": reason},
    )
    return {"merge_id": merge_id, "canonical_venue_id": canonical_id, "merged_venue_id": merged_id}


def undo_merge(conn: Connection, workspace_id: UUID, actor: str, merge_id: UUID) -> dict[str, Any]:
    row = conn.execute(
        text(
            "SELECT id, merged_venue_id, is_undone FROM venue_merge WHERE id = :id"
        ),
        {"id": merge_id},
    ).mappings().first()
    if row is None:
        raise ValueError("merge_not_found")
    if row["is_undone"]:
        raise ValueError("already_undone")
    merged_id = row["merged_venue_id"]
    conn.execute(
        text("UPDATE venue SET merged_into_id = NULL, status = 'active' WHERE id = :m"),
        {"m": merged_id},
    )
    conn.execute(
        text("UPDATE venue_merge SET is_undone = true, undone_at = now(), undone_by = :actor WHERE id = :id"),
        {"actor": actor, "id": merge_id},
    )
    audit.write_audit(
        conn, workspace_id, actor, "venue.merge.undo", entity="venue",
        entity_id=str(merged_id), after={"merge_id": str(merge_id)},
    )
    return {"merge_id": merge_id, "merged_venue_id": merged_id, "undone": True}
