"""Person affiliations — roles & participation (Phase 5, Stage 2).

A person's involvement with clubs, teams, associations and competitions over a career: multiple
and concurrent affiliations, transfers, returns to former clubs, representative participation and
multiple roles within one organisation, each time-bounded (periods may be unknown/approximate).

**Affiliation is membership/involvement, not match participation.** Nothing here establishes that
a person played, captained or kept wicket in a match — those come only from match records
(Phase 8). ``role`` is free text so the role set is extensible without a schema change; the
standard roles are listed in :data:`STANDARD_ROLES` for UI suggestions. Historical research is
supported via verification status, evidence, notes and provenance; unknown dates stay unknown and
participation is never inferred from insufficient evidence.

Workspace-scoped (RLS); governed by ``person.manage``; all mutations audited. Rhymney / Moyston /
Rhymney-Moyston remain distinct organisations — a person may hold affiliations to each across
different periods with attribution preserved; combined career reporting is an explicit approved
reporting rule, never an automatic statistic merge.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

# Standard roles (UI suggestions). The column is free text, so new roles need no migration.
STANDARD_ROLES = (
    "player", "captain", "vice_captain", "coach", "assistant_coach", "team_manager",
    "umpire", "scorer", "club_official", "association_official", "life_member", "honorary_member",
)
VERIFICATION_STATUSES = ("unverified", "verified", "disputed", "corrected")

_COLS = (
    "id, workspace_id, person_id, organisation_id, team_id, competition_id, role, "
    "valid_from, valid_to, date_approx, is_representative, is_temporary, status, verification_status, "
    "evidence, notes, source_system, source_ref, created_at"
)


def get_affiliation(conn: Connection, affiliation_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(
        text(f"SELECT {_COLS} FROM person_affiliation WHERE id = :id"), {"id": affiliation_id}
    ).mappings().first()
    return dict(r) if r else None


def list_affiliations(
    conn: Connection, *, person_id: UUID | None = None, organisation_id: UUID | None = None,
    role: str | None = None,
) -> list[dict[str, Any]]:
    sql = f"SELECT {_COLS} FROM person_affiliation"
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if person_id is not None:
        clauses.append("person_id = :p")
        params["p"] = person_id
    if organisation_id is not None:
        clauses.append("organisation_id = :o")
        params["o"] = organisation_id
    if role is not None:
        clauses.append("role = :r")
        params["r"] = role
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY valid_from NULLS FIRST, created_at"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def create_affiliation(
    conn: Connection, workspace_id: UUID, actor: str, *, person_id: UUID, organisation_id: UUID,
    role: str = "player", team_id: UUID | None = None, competition_id: UUID | None = None,
    valid_from: Any | None = None, valid_to: Any | None = None, date_approx: bool = False,
    is_representative: bool = False, is_temporary: bool = False, verification_status: str = "unverified",
    evidence: str | None = None, notes: str | None = None,
    source_system: str | None = None, source_ref: str | None = None,
) -> UUID:
    role = (role or "").strip()
    if not role:
        raise ValueError("missing_role")
    if verification_status not in VERIFICATION_STATUSES:
        raise ValueError("invalid_verification_status")
    if conn.execute(text("SELECT 1 FROM person WHERE id = :p"), {"p": person_id}).first() is None:
        raise ValueError("person_not_found")
    if conn.execute(text("SELECT 1 FROM organisation WHERE id = :o"), {"o": organisation_id}).first() is None:
        raise ValueError("organisation_not_found")
    if team_id is not None and conn.execute(
        text("SELECT 1 FROM team WHERE id = :t AND organisation_id = :o"),
        {"t": team_id, "o": organisation_id},
    ).first() is None:
        raise ValueError("team_not_in_organisation")
    if valid_from is not None and valid_to is not None and valid_to < valid_from:
        raise ValueError("invalid_date_range")
    aff_id = conn.execute(
        text(
            "INSERT INTO person_affiliation"
            "(workspace_id, person_id, organisation_id, team_id, competition_id, role, valid_from, "
            " valid_to, date_approx, is_representative, is_temporary, verification_status, evidence, "
            " notes, source_system, source_ref) "
            "VALUES (:w, :p, :o, :t, :c, :role, :vf, :vt, :approx, :rep, :tmp, :vs, :ev, :notes, :ss, :sr) "
            "RETURNING id"
        ),
        {"w": workspace_id, "p": person_id, "o": organisation_id, "t": team_id, "c": competition_id,
         "role": role, "vf": valid_from, "vt": valid_to, "approx": date_approx, "rep": is_representative,
         "tmp": is_temporary, "vs": verification_status, "ev": evidence, "notes": notes,
         "ss": source_system, "sr": source_ref},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "person_affiliation.create", entity="person_affiliation",
                      entity_id=str(aff_id),
                      after={"person_id": str(person_id), "organisation_id": str(organisation_id),
                             "role": role, "valid_from": str(valid_from) if valid_from else None})
    return aff_id


def correct_affiliation(
    conn: Connection, workspace_id: UUID, actor: str, affiliation_id: UUID, *,
    role: str | None = None, team_id: UUID | None = None, valid_from: Any | None = None,
    valid_to: Any | None = None, set_dates: bool = False, date_approx: bool | None = None,
    is_representative: bool | None = None, status: str | None = None,
    evidence: str | None = None, notes: str | None = None,
) -> dict[str, Any]:
    before = get_affiliation(conn, affiliation_id)
    if before is None:
        raise ValueError("affiliation_not_found")
    sets, params = [], {"id": affiliation_id}
    if role is not None:
        role = role.strip()
        if not role:
            raise ValueError("missing_role")
        sets.append("role = :role")
        params["role"] = role
    if team_id is not None:
        if conn.execute(
            text("SELECT 1 FROM team WHERE id = :t AND organisation_id = :o"),
            {"t": team_id, "o": before["organisation_id"]},
        ).first() is None:
            raise ValueError("team_not_in_organisation")
        sets.append("team_id = :t")
        params["t"] = team_id
    if set_dates:
        if valid_from is not None and valid_to is not None and valid_to < valid_from:
            raise ValueError("invalid_date_range")
        sets += ["valid_from = :vf", "valid_to = :vt"]
        params["vf"] = valid_from
        params["vt"] = valid_to
    for col, val in (("date_approx", date_approx), ("is_representative", is_representative)):
        if val is not None:
            sets.append(f"{col} = :{col}")
            params[col] = val
    if status is not None:
        sets.append("status = :st")
        params["st"] = status
    if evidence is not None:
        sets.append("evidence = :ev")
        params["ev"] = evidence
    if notes is not None:
        sets.append("notes = :notes")
        params["notes"] = notes
    if sets:
        conn.execute(text(f"UPDATE person_affiliation SET {', '.join(sets)} WHERE id = :id"), params)
    after = get_affiliation(conn, affiliation_id)
    audit.write_audit(conn, workspace_id, actor, "person_affiliation.correct", entity="person_affiliation",
                      entity_id=str(affiliation_id), before=before, after=after)
    return after


def set_verification(
    conn: Connection, workspace_id: UUID, actor: str, affiliation_id: UUID, *, status: str,
) -> dict[str, Any]:
    before = get_affiliation(conn, affiliation_id)
    if before is None:
        raise ValueError("affiliation_not_found")
    if status not in VERIFICATION_STATUSES:
        raise ValueError("invalid_verification_status")
    conn.execute(
        text("UPDATE person_affiliation SET verification_status = :vs WHERE id = :id"),
        {"vs": status, "id": affiliation_id},
    )
    after = get_affiliation(conn, affiliation_id)
    audit.write_audit(conn, workspace_id, actor, "person_affiliation.verify", entity="person_affiliation",
                      entity_id=str(affiliation_id), before=before, after=after)
    return after


def person_career(conn: Connection, person_id: UUID) -> list[dict[str, Any]]:
    """All affiliations for a person, chronologically (unknown-dated first), across every
    organisation — attribution preserved per distinct organisation."""
    return list_affiliations(conn, person_id=person_id)


def affiliations_as_of(conn: Connection, person_id: UUID, on_date: Any) -> list[dict[str, Any]]:
    """Affiliations active on a date (concurrent affiliations are allowed and all returned)."""
    rows = conn.execute(
        text(
            f"SELECT {_COLS} FROM person_affiliation WHERE person_id = :p "
            "AND (valid_from IS NULL OR valid_from <= :d) AND (valid_to IS NULL OR valid_to >= :d) "
            "ORDER BY organisation_id"
        ),
        {"p": person_id, "d": on_date},
    ).mappings().all()
    return [dict(r) for r in rows]
