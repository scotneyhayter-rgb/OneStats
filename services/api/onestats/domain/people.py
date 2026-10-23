"""People & player identity (Phase 5, Stage 1).

Unique, persistent person identities for all cricket participants, with multiple roles per
person, historical names/aliases/initials/incomplete names, external source provenance, and
unknown-aware personal data (optional DOB with precision; Cricket Statz ``1700-01-01`` → unknown).
A person is never duplicated for representing different clubs, and same-name/same-initials people
are never auto-merged — this module only *suggests* possible duplicates for later (Stage 3)
administrator-approved, reversible resolution. Junior personal data is privacy-protected by
default. Workspace-scoped (RLS); governed by ``person.manage``; all mutations audited.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

ROLES = ("player", "umpire", "scorer", "coach", "administrator", "selector", "captain", "other")
NAME_TYPES = ("primary", "alias", "initials", "maiden", "incomplete", "other")
DOB_PRECISIONS = ("unknown", "exact", "year", "month", "approx")
# Cricket Statz placeholder DOB — never a genuine birth date.
CS_UNKNOWN_DOB = "1700-01-01"

_COLS = (
    "id, workspace_id, display_name, status, is_junior, privacy_protected, dob, dob_precision, "
    "notes, merged_into_id, source_system, source_ref, created_at"
)
# Fields hidden by default for privacy-protected (e.g. junior) people.
_PROTECTED_FIELDS = ("dob", "dob_precision", "notes")


def _normalise(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _redact(row: dict[str, Any], include_protected: bool) -> dict[str, Any]:
    if row.get("privacy_protected") and not include_protected:
        row = dict(row)
        for f in _PROTECTED_FIELDS:
            row[f] = None
        row["protected_fields_hidden"] = True
    return row


# --------------------------------------------------------------------------- reads


def get_person(conn: Connection, person_id: UUID, *, include_protected: bool = False) -> dict[str, Any] | None:
    row = conn.execute(
        text(f"SELECT {_COLS} FROM person WHERE id = :id"), {"id": person_id}
    ).mappings().first()
    return _redact(dict(row), include_protected) if row else None


def list_people(
    conn: Connection, *, search: str | None = None, role: str | None = None,
    include_merged: bool = False, include_protected: bool = False,
) -> list[dict[str, Any]]:
    sql = f"SELECT {_COLS} FROM person"
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if not include_merged:
        clauses.append("merged_into_id IS NULL")
    if search:
        clauses.append("display_name ILIKE :q")
        params["q"] = f"%{search}%"
    if role:
        clauses.append("id IN (SELECT person_id FROM person_role WHERE role = :role)")
        params["role"] = role
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY display_name"
    return [_redact(dict(r), include_protected) for r in conn.execute(text(sql), params).mappings().all()]


def list_names(conn: Connection, person_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT id, name, name_type, valid_from, valid_to, note, created_at "
            "FROM person_name_history WHERE person_id = :p ORDER BY valid_from NULLS FIRST, created_at"
        ),
        {"p": person_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def list_source_identities(conn: Connection, person_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT id, source_system, source_ref, source_display_name, created_at "
            "FROM person_source_identity WHERE person_id = :p ORDER BY source_system, source_ref"
        ),
        {"p": person_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def list_roles(conn: Connection, person_id: UUID) -> list[str]:
    return list(
        conn.execute(
            text("SELECT role FROM person_role WHERE person_id = :p ORDER BY role"), {"p": person_id}
        ).scalars().all()
    )


def detail(conn: Connection, person_id: UUID, *, include_protected: bool = False) -> dict[str, Any] | None:
    person = get_person(conn, person_id, include_protected=include_protected)
    if person is None:
        return None
    person["names"] = list_names(conn, person_id)
    person["source_identities"] = list_source_identities(conn, person_id)
    person["roles"] = list_roles(conn, person_id)
    return person


def name_as_of(conn: Connection, person_id: UUID, on_date: Any) -> str | None:
    row = conn.execute(
        text(
            "SELECT name FROM person_name_history WHERE person_id = :p "
            "AND (valid_from IS NULL OR valid_from <= :d) AND (valid_to IS NULL OR valid_to >= :d) "
            "ORDER BY valid_from DESC NULLS LAST, created_at DESC LIMIT 1"
        ),
        {"p": person_id, "d": on_date},
    ).scalar_one_or_none()
    if row is not None:
        return row
    return conn.execute(
        text("SELECT name FROM person_name_history WHERE person_id = :p ORDER BY valid_from NULLS FIRST, created_at LIMIT 1"),
        {"p": person_id},
    ).scalar_one_or_none()


# --------------------------------------------------------------------------- writes


def _clean_dob(dob: Any, precision: str) -> tuple[Any, str]:
    """Map Cricket Statz placeholder / blank DOB to unknown; never a genuine birth date."""
    if dob in (None, "", CS_UNKNOWN_DOB):
        return None, "unknown"
    if precision not in DOB_PRECISIONS:
        precision = "exact"
    return dob, precision


def create_person(
    conn: Connection, workspace_id: UUID, actor: str, *, display_name: str,
    dob: Any | None = None, dob_precision: str = "unknown", is_junior: bool = False,
    privacy_protected: bool | None = None, notes: str | None = None,
    roles: list[str] | None = None, source_system: str | None = None, source_ref: str | None = None,
) -> UUID:
    display_name = (display_name or "").strip()
    if not display_name:
        raise ValueError("missing_name")
    dob, dob_precision = _clean_dob(dob, dob_precision)
    # Juniors are always privacy-protected; otherwise honour the flag (default protected off).
    protected = True if is_junior else bool(privacy_protected)
    for r in roles or []:
        if r not in ROLES:
            raise ValueError("invalid_role")
    person_id = conn.execute(
        text(
            "INSERT INTO person"
            "(workspace_id, display_name, is_junior, privacy_protected, dob, dob_precision, notes, "
            " source_system, source_ref) "
            "VALUES (:w, :n, :j, :pp, :dob, :prec, :notes, :ss, :sr) RETURNING id"
        ),
        {"w": workspace_id, "n": display_name, "j": is_junior, "pp": protected, "dob": dob,
         "prec": dob_precision, "notes": notes, "ss": source_system, "sr": source_ref},
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO person_name_history(workspace_id, person_id, name, name_type, note) "
            "VALUES (:w, :p, :n, 'primary', 'initial name')"
        ),
        {"w": workspace_id, "p": person_id, "n": display_name},
    )
    for r in roles or []:
        conn.execute(
            text(
                "INSERT INTO person_role(workspace_id, person_id, role) VALUES (:w, :p, :r) "
                "ON CONFLICT ON CONSTRAINT uq_person_role DO NOTHING"
            ),
            {"w": workspace_id, "p": person_id, "r": r},
        )
    if source_system and source_ref:
        add_source_identity(conn, workspace_id, actor, person_id,
                            source_system=source_system, source_ref=source_ref,
                            source_display_name=display_name, _audit=False)
    audit.write_audit(conn, workspace_id, actor, "person.create", entity="person",
                      entity_id=str(person_id),
                      after={"display_name": display_name, "is_junior": is_junior, "roles": roles or []})
    return person_id


def update_person(
    conn: Connection, workspace_id: UUID, actor: str, person_id: UUID, *,
    display_name: str | None = None, status: str | None = None, is_junior: bool | None = None,
    privacy_protected: bool | None = None, dob: Any | None = None, dob_precision: str | None = None,
    notes: str | None = None, set_dob: bool = False, name_change_note: str | None = None,
) -> dict[str, Any]:
    before = get_person(conn, person_id, include_protected=True)
    if before is None:
        raise ValueError("person_not_found")
    new_name = display_name.strip() if display_name is not None else None
    if display_name is not None and not new_name:
        raise ValueError("missing_name")
    sets, params = [], {"id": person_id}
    if new_name:
        sets.append("display_name = :n")
        params["n"] = new_name
    if status is not None:
        sets.append("status = :st")
        params["st"] = status
    if is_junior is not None:
        sets.append("is_junior = :j")
        params["j"] = is_junior
        # Promoting to junior forces privacy protection on.
        if is_junior:
            sets.append("privacy_protected = true")
    if privacy_protected is not None and not (is_junior):
        sets.append("privacy_protected = :pp")
        params["pp"] = privacy_protected
    if notes is not None:
        sets.append("notes = :notes")
        params["notes"] = notes
    if set_dob:
        d, prec = _clean_dob(dob, dob_precision or "exact")
        sets += ["dob = :dob", "dob_precision = :prec"]
        params["dob"] = d
        params["prec"] = prec
    if sets:
        conn.execute(text(f"UPDATE person SET {', '.join(sets)} WHERE id = :id"), params)
    if new_name and new_name != before["display_name"]:
        conn.execute(
            text(
                "INSERT INTO person_name_history(workspace_id, person_id, name, name_type, note) "
                "VALUES (:w, :p, :n, 'primary', :note)"
            ),
            {"w": workspace_id, "p": person_id, "n": new_name, "note": name_change_note or "renamed"},
        )
    after = get_person(conn, person_id, include_protected=True)
    audit.write_audit(conn, workspace_id, actor, "person.update", entity="person",
                      entity_id=str(person_id), before=before, after=after)
    return after


def add_name(
    conn: Connection, workspace_id: UUID, actor: str, person_id: UUID, *, name: str,
    name_type: str = "alias", valid_from: Any | None = None, valid_to: Any | None = None,
    note: str | None = None,
) -> UUID:
    name = (name or "").strip()
    if not name:
        raise ValueError("missing_name")
    if name_type not in NAME_TYPES:
        raise ValueError("invalid_name_type")
    if get_person(conn, person_id, include_protected=True) is None:
        raise ValueError("person_not_found")
    nid = conn.execute(
        text(
            "INSERT INTO person_name_history(workspace_id, person_id, name, name_type, valid_from, valid_to, note) "
            "VALUES (:w, :p, :n, :t, :vf, :vt, :note) RETURNING id"
        ),
        {"w": workspace_id, "p": person_id, "n": name, "t": name_type, "vf": valid_from, "vt": valid_to, "note": note},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "person.name.add", entity="person",
                      entity_id=str(person_id), after={"name": name, "name_type": name_type})
    return nid


def add_source_identity(
    conn: Connection, workspace_id: UUID, actor: str, person_id: UUID, *,
    source_system: str, source_ref: str, source_display_name: str | None = None, _audit: bool = True,
) -> dict[str, Any]:
    if not source_system or not source_ref:
        raise ValueError("missing_source_ref")
    existing = conn.execute(
        text(
            "SELECT id, person_id, source_system, source_ref, source_display_name "
            "FROM person_source_identity WHERE source_system = :ss AND source_ref = :sr"
        ),
        {"ss": source_system, "sr": source_ref},
    ).mappings().first()
    if existing is not None:
        return dict(existing) | {"created": False}
    row = conn.execute(
        text(
            "INSERT INTO person_source_identity"
            "(workspace_id, person_id, source_system, source_ref, source_display_name) "
            "VALUES (:w, :p, :ss, :sr, :dn) "
            "RETURNING id, person_id, source_system, source_ref, source_display_name"
        ),
        {"w": workspace_id, "p": person_id, "ss": source_system, "sr": source_ref, "dn": source_display_name},
    ).mappings().one()
    if _audit:
        audit.write_audit(conn, workspace_id, actor, "person.source_identity.add", entity="person",
                          entity_id=str(person_id), after={"source_system": source_system, "source_ref": source_ref})
    return dict(row) | {"created": True}


def add_role(conn: Connection, workspace_id: UUID, actor: str, person_id: UUID, role: str) -> dict[str, Any]:
    if role not in ROLES:
        raise ValueError("invalid_role")
    if get_person(conn, person_id, include_protected=True) is None:
        raise ValueError("person_not_found")
    existing = conn.execute(
        text("SELECT id FROM person_role WHERE person_id = :p AND role = :r"),
        {"p": person_id, "r": role},
    ).scalar_one_or_none()
    if existing is not None:
        return {"role_id": existing, "created": False}
    rid = conn.execute(
        text("INSERT INTO person_role(workspace_id, person_id, role) VALUES (:w, :p, :r) RETURNING id"),
        {"w": workspace_id, "p": person_id, "r": role},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "person.role.add", entity="person",
                      entity_id=str(person_id), after={"role": role})
    return {"role_id": rid, "created": True}


def remove_role(conn: Connection, workspace_id: UUID, actor: str, person_id: UUID, role: str) -> bool:
    res = conn.execute(
        text("DELETE FROM person_role WHERE person_id = :p AND role = :r"), {"p": person_id, "r": role}
    )
    removed = res.rowcount > 0
    if removed:
        audit.write_audit(conn, workspace_id, actor, "person.role.remove", entity="person",
                          entity_id=str(person_id), after={"role": role})
    return removed


def find_duplicate_candidates(conn: Connection, person_id: UUID) -> list[dict[str, Any]]:
    """Suggest possible duplicate people for later administrator review. Shared source identity is
    strong evidence; an identical normalised name/initials is weak. NEVER merges and NEVER treats a
    shared name or initials alone as proof (two "A Bonner" may be different people). Stage 3 adds the
    reversible, admin-approved merge and distinct-person assertions."""
    person = get_person(conn, person_id, include_protected=True)
    if person is None:
        raise ValueError("person_not_found")
    candidates: dict[UUID, dict[str, Any]] = {}

    shared = conn.execute(
        text(
            "SELECT DISTINCT other.person_id AS pid FROM person_source_identity mine "
            "JOIN person_source_identity other "
            "  ON other.source_system = mine.source_system AND other.source_ref = mine.source_ref "
            "WHERE mine.person_id = :p AND other.person_id <> :p"
        ),
        {"p": person_id},
    ).scalars().all()
    for pid in shared:
        candidates.setdefault(pid, {"evidence": []})["evidence"].append("shared_source_identity")

    key = _normalise(person["display_name"])
    same_name = conn.execute(
        text(
            "SELECT id FROM person WHERE id <> :p AND merged_into_id IS NULL "
            "AND regexp_replace(lower(btrim(display_name)), '\\s+', ' ', 'g') = :k"
        ),
        {"p": person_id, "k": key},
    ).scalars().all()
    for pid in same_name:
        candidates.setdefault(pid, {"evidence": []})["evidence"].append("same_normalised_name")

    results: list[dict[str, Any]] = []
    for pid, info in candidates.items():
        cand = get_person(conn, pid, include_protected=False)
        if cand is None or cand["merged_into_id"] is not None:
            continue
        results.append({
            "person_id": pid, "display_name": cand["display_name"], "evidence": info["evidence"],
            # A name/initials match alone is only ever WEAK — never proof of same identity.
            "confidence": "strong" if "shared_source_identity" in info["evidence"] else "weak",
        })
    results.sort(key=lambda r: (r["confidence"] != "strong", r["display_name"]))
    return results
