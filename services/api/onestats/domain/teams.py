"""Teams & their historical identity (Phase 4, Stage 2).

A team is the side an organisation fields in a given cricket *program* (seniors, juniors,
women's, girls', all-abilities, veterans, …). Teams carry stable identifiers and the same
conservative identity machinery as organisations/venues: period-correct name history, external
source identities, evidence-based duplicate *suggestions*, administrator-approved reversible
merges, and explicit "definitely different" assertions.

A team is attributable to an organisation and program; a merger or rename never silently
reassigns a historical team to a later organisation — the merged record is preserved and the
move is explicit, audited and reversible. Season-specific competition entries arrive in Stage 3.
Callers must have set the workspace context so RLS scopes all reads and writes to the workspace.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

_PROGRAMS = ("seniors", "juniors", "womens", "girls", "all_abilities", "veterans", "custom")
_COLS = (
    "id, workspace_id, organisation_id, name, short_name, program, is_historical, status, "
    "notes, merged_into_id, source_system, source_ref, created_at"
)
# First/last recorded match YEAR for a team — the span of its recorded match history (every dated match
# the team appeared in, approved or not; correlated on the outer `team` row). NULL when it has none.
_TEAM_SPAN = (
    ", (SELECT extract(year FROM min(m.match_date))::int FROM match m "
    "   JOIN match_team mt ON mt.match_id = m.id "
    "   WHERE mt.team_id = team.id AND m.match_date IS NOT NULL) AS first_match_year"
    ", (SELECT extract(year FROM max(m.match_date))::int FROM match m "
    "   JOIN match_team mt ON mt.match_id = m.id "
    "   WHERE mt.team_id = team.id AND m.match_date IS NOT NULL) AS last_match_year"
)
_MAX_CHAIN = 16


def _normalise_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _ordered_pair(a: UUID, b: UUID) -> tuple[UUID, UUID]:
    return (a, b) if str(a) <= str(b) else (b, a)


# --------------------------------------------------------------------------- reads


def get_team(conn: Connection, team_id: UUID) -> dict[str, Any] | None:
    row = conn.execute(
        text(f"SELECT {_COLS} FROM team WHERE id = :id"), {"id": team_id}
    ).mappings().first()
    return dict(row) if row else None


def list_teams(
    conn: Connection, *, organisation_id: UUID | None = None, program: str | None = None,
    include_merged: bool = False, search: str | None = None,
) -> list[dict[str, Any]]:
    sql = f"SELECT {_COLS}{_TEAM_SPAN} FROM team"
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if not include_merged:
        clauses.append("merged_into_id IS NULL")
    if organisation_id is not None:
        clauses.append("organisation_id = :org")
        params["org"] = organisation_id
    if program is not None:
        clauses.append("program = :prog")
        params["prog"] = program
    if search:
        clauses.append("name ILIKE :q")
        params["q"] = f"%{search}%"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY name"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def list_name_history(conn: Connection, team_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT id, name, valid_from, valid_to, note, created_at "
            "FROM team_name_history WHERE team_id = :o ORDER BY valid_from NULLS FIRST, created_at"
        ),
        {"o": team_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def list_source_identities(conn: Connection, team_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT id, source_system, source_ref, source_display_name, created_at "
            "FROM team_source_identity WHERE team_id = :o ORDER BY source_system, source_ref"
        ),
        {"o": team_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def name_as_of(conn: Connection, team_id: UUID, on_date: Any) -> str | None:
    row = conn.execute(
        text(
            "SELECT name FROM team_name_history WHERE team_id = :o "
            "AND (valid_from IS NULL OR valid_from <= :d) "
            "AND (valid_to IS NULL OR valid_to >= :d) "
            "ORDER BY valid_from DESC NULLS LAST, created_at DESC LIMIT 1"
        ),
        {"o": team_id, "d": on_date},
    ).scalar_one_or_none()
    if row is not None:
        return row
    return conn.execute(
        text(
            "SELECT name FROM team_name_history WHERE team_id = :o "
            "ORDER BY valid_from NULLS FIRST, created_at LIMIT 1"
        ),
        {"o": team_id},
    ).scalar_one_or_none()


def resolve_canonical(conn: Connection, team_id: UUID) -> UUID:
    current = team_id
    for _ in range(_MAX_CHAIN):
        nxt = conn.execute(
            text("SELECT merged_into_id FROM team WHERE id = :id"), {"id": current}
        ).scalar_one_or_none()
        if nxt is None:
            return current
        current = nxt
    raise ValueError("merge_chain_too_deep")


# --------------------------------------------------------------------------- writes


def create_team(
    conn: Connection,
    workspace_id: UUID,
    actor: str,
    *,
    organisation_id: UUID,
    name: str,
    program: str = "seniors",
    short_name: str | None = None,
    is_historical: bool = False,
    notes: str | None = None,
    source_system: str | None = None,
    source_ref: str | None = None,
) -> UUID:
    name = (name or "").strip()
    if not name:
        raise ValueError("missing_name")
    if program not in _PROGRAMS:
        raise ValueError("invalid_program")
    # The organisation must exist in this workspace (RLS already scopes visibility).
    if conn.execute(
        text("SELECT 1 FROM organisation WHERE id = :o"), {"o": organisation_id}
    ).first() is None:
        raise ValueError("organisation_not_found")
    team_id = conn.execute(
        text(
            "INSERT INTO team"
            "(workspace_id, organisation_id, name, short_name, program, is_historical, notes, "
            " source_system, source_ref) "
            "VALUES (:w, :org, :n, :sn, :p, :h, :notes, :ss, :sr) RETURNING id"
        ),
        {
            "w": workspace_id, "org": organisation_id, "n": name, "sn": short_name,
            "p": program, "h": is_historical, "notes": notes,
            "ss": source_system, "sr": source_ref,
        },
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO team_name_history(workspace_id, team_id, name, note) "
            "VALUES (:w, :o, :n, 'initial name')"
        ),
        {"w": workspace_id, "o": team_id, "n": name},
    )
    if source_system and source_ref:
        add_source_identity(
            conn, workspace_id, actor, team_id,
            source_system=source_system, source_ref=source_ref, source_display_name=name, _audit=False,
        )
    audit.write_audit(
        conn, workspace_id, actor, "team.create", entity="team", entity_id=str(team_id),
        after={"name": name, "program": program, "organisation_id": str(organisation_id),
               "is_historical": is_historical},
    )
    return team_id


def update_team(
    conn: Connection,
    workspace_id: UUID,
    actor: str,
    team_id: UUID,
    *,
    name: str | None = None,
    short_name: str | None = None,
    program: str | None = None,
    status: str | None = None,
    is_historical: bool | None = None,
    notes: str | None = None,
    name_change_note: str | None = None,
) -> dict[str, Any]:
    before = get_team(conn, team_id)
    if before is None:
        raise ValueError("team_not_found")
    if program is not None and program not in _PROGRAMS:
        raise ValueError("invalid_program")
    new_name = name.strip() if name is not None else None
    if name is not None and not new_name:
        raise ValueError("missing_name")
    conn.execute(
        text(
            "UPDATE team SET name = coalesce(:n, name), short_name = coalesce(:sn, short_name), "
            "program = coalesce(:p, program), status = coalesce(:st, status), "
            "is_historical = coalesce(:h, is_historical), notes = coalesce(:notes, notes) "
            "WHERE id = :id"
        ),
        {"n": new_name, "sn": short_name, "p": program, "st": status,
         "h": is_historical, "notes": notes, "id": team_id},
    )
    if new_name and new_name != before["name"]:
        conn.execute(
            text(
                "INSERT INTO team_name_history(workspace_id, team_id, name, note) "
                "VALUES (:w, :o, :n, :note)"
            ),
            {"w": workspace_id, "o": team_id, "n": new_name, "note": name_change_note or "renamed"},
        )
    after = get_team(conn, team_id)
    audit.write_audit(
        conn, workspace_id, actor, "team.update", entity="team", entity_id=str(team_id),
        before=before, after=after,
    )
    return after


def add_name_history(
    conn: Connection, workspace_id: UUID, actor: str, team_id: UUID,
    *, name: str, valid_from: Any | None = None, valid_to: Any | None = None, note: str | None = None,
) -> UUID:
    name = (name or "").strip()
    if not name:
        raise ValueError("missing_name")
    if get_team(conn, team_id) is None:
        raise ValueError("team_not_found")
    hist_id = conn.execute(
        text(
            "INSERT INTO team_name_history(workspace_id, team_id, name, valid_from, valid_to, note) "
            "VALUES (:w, :o, :n, :vf, :vt, :note) RETURNING id"
        ),
        {"w": workspace_id, "o": team_id, "n": name, "vf": valid_from, "vt": valid_to, "note": note},
    ).scalar_one()
    audit.write_audit(
        conn, workspace_id, actor, "team.name_history.add", entity="team",
        entity_id=str(team_id), after={"name": name},
    )
    return hist_id


def add_source_identity(
    conn: Connection, workspace_id: UUID, actor: str, team_id: UUID,
    *, source_system: str, source_ref: str, source_display_name: str | None = None, _audit: bool = True,
) -> dict[str, Any]:
    if not source_system or not source_ref:
        raise ValueError("missing_source_ref")
    existing = conn.execute(
        text(
            "SELECT id, team_id, source_system, source_ref, source_display_name "
            "FROM team_source_identity WHERE source_system = :ss AND source_ref = :sr"
        ),
        {"ss": source_system, "sr": source_ref},
    ).mappings().first()
    if existing is not None:
        return dict(existing) | {"created": False}
    row = conn.execute(
        text(
            "INSERT INTO team_source_identity"
            "(workspace_id, team_id, source_system, source_ref, source_display_name) "
            "VALUES (:w, :o, :ss, :sr, :dn) "
            "RETURNING id, team_id, source_system, source_ref, source_display_name"
        ),
        {"w": workspace_id, "o": team_id, "ss": source_system, "sr": source_ref, "dn": source_display_name},
    ).mappings().one()
    if _audit:
        audit.write_audit(
            conn, workspace_id, actor, "team.source_identity.add", entity="team",
            entity_id=str(team_id), after={"source_system": source_system, "source_ref": source_ref},
        )
    return dict(row) | {"created": True}


# ----------------------------------------------------------------- distinct assertions


def are_asserted_distinct(conn: Connection, a: UUID, b: UUID) -> bool:
    x, y = _ordered_pair(a, b)
    return conn.execute(
        text("SELECT 1 FROM team_distinct_assertion WHERE team_a_id = :a AND team_b_id = :b"),
        {"a": x, "b": y},
    ).first() is not None


def assert_distinct(
    conn: Connection, workspace_id: UUID, actor: str, a: UUID, b: UUID, *, reason: str | None = None
) -> UUID:
    if a == b:
        raise ValueError("same_team")
    for tid in (a, b):
        if get_team(conn, tid) is None:
            raise ValueError("team_not_found")
    x, y = _ordered_pair(a, b)
    existing = conn.execute(
        text("SELECT id FROM team_distinct_assertion WHERE team_a_id = :a AND team_b_id = :b"),
        {"a": x, "b": y},
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    assertion_id = conn.execute(
        text(
            "INSERT INTO team_distinct_assertion(workspace_id, team_a_id, team_b_id, actor, reason) "
            "VALUES (:w, :a, :b, :actor, :reason) RETURNING id"
        ),
        {"w": workspace_id, "a": x, "b": y, "actor": actor, "reason": reason},
    ).scalar_one()
    audit.write_audit(
        conn, workspace_id, actor, "team.assert_distinct", entity="team",
        entity_id=str(x), after={"team_a_id": str(x), "team_b_id": str(y), "reason": reason},
    )
    return assertion_id


# ----------------------------------------------------------------- duplicate review


def find_duplicate_candidates(conn: Connection, team_id: UUID) -> list[dict[str, Any]]:
    """Suggest possible duplicate teams for human review. Shared source identity = strong;
    identical normalised name *within the same organisation and program* = weak. Never merges,
    and a name match alone is never treated as proof."""
    team = get_team(conn, team_id)
    if team is None:
        raise ValueError("team_not_found")
    candidates: dict[UUID, dict[str, Any]] = {}

    shared = conn.execute(
        text(
            "SELECT DISTINCT other.team_id AS oid FROM team_source_identity mine "
            "JOIN team_source_identity other "
            "  ON other.source_system = mine.source_system AND other.source_ref = mine.source_ref "
            "WHERE mine.team_id = :o AND other.team_id <> :o"
        ),
        {"o": team_id},
    ).scalars().all()
    for oid in shared:
        candidates.setdefault(oid, {"evidence": []})["evidence"].append("shared_source_identity")

    # Name match is scoped to the same organisation + program: two clubs' "First XI" are NOT dupes.
    key = _normalise_name(team["name"])
    same_name = conn.execute(
        text(
            "SELECT id FROM team WHERE id <> :o AND merged_into_id IS NULL "
            "AND organisation_id = :org AND program = :prog "
            "AND regexp_replace(lower(btrim(name)), '\\s+', ' ', 'g') = :k"
        ),
        {"o": team_id, "org": team["organisation_id"], "prog": team["program"], "k": key},
    ).scalars().all()
    for oid in same_name:
        candidates.setdefault(oid, {"evidence": []})["evidence"].append("same_name_org_program")

    results: list[dict[str, Any]] = []
    for oid, info in candidates.items():
        if are_asserted_distinct(conn, team_id, oid):
            continue
        cand = get_team(conn, oid)
        if cand is None or cand["merged_into_id"] is not None:
            continue
        results.append({
            "team_id": oid, "name": cand["name"], "evidence": info["evidence"],
            "confidence": "strong" if "shared_source_identity" in info["evidence"] else "weak",
        })
    results.sort(key=lambda r: (r["confidence"] != "strong", r["name"]))
    return results


# ----------------------------------------------------------------- merge / undo


def merge_teams(
    conn: Connection, workspace_id: UUID, actor: str, canonical_id: UUID, merged_id: UUID,
    *, reason: str | None = None,
) -> dict[str, Any]:
    if canonical_id == merged_id:
        raise ValueError("cannot_merge_same")
    canonical = get_team(conn, canonical_id)
    merged = get_team(conn, merged_id)
    if canonical is None or merged is None:
        raise ValueError("team_not_found")
    if canonical["merged_into_id"] is not None:
        raise ValueError("canonical_already_merged")
    if merged["merged_into_id"] is not None:
        raise ValueError("already_merged")
    if are_asserted_distinct(conn, canonical_id, merged_id):
        raise ValueError("asserted_distinct")
    conn.execute(
        text("UPDATE team SET merged_into_id = :c, status = 'merged' WHERE id = :m"),
        {"c": canonical_id, "m": merged_id},
    )
    merge_id = conn.execute(
        text(
            "INSERT INTO team_merge(workspace_id, canonical_team_id, merged_team_id, actor, reason) "
            "VALUES (:w, :c, :m, :actor, :reason) RETURNING id"
        ),
        {"w": workspace_id, "c": canonical_id, "m": merged_id, "actor": actor, "reason": reason},
    ).scalar_one()
    audit.write_audit(
        conn, workspace_id, actor, "team.merge", entity="team", entity_id=str(merged_id),
        after={"canonical_team_id": str(canonical_id), "merged_team_id": str(merged_id), "reason": reason},
    )
    return {"merge_id": merge_id, "canonical_team_id": canonical_id, "merged_team_id": merged_id}


def undo_merge(conn: Connection, workspace_id: UUID, actor: str, merge_id: UUID) -> dict[str, Any]:
    row = conn.execute(
        text("SELECT id, merged_team_id, is_undone FROM team_merge WHERE id = :id"),
        {"id": merge_id},
    ).mappings().first()
    if row is None:
        raise ValueError("merge_not_found")
    if row["is_undone"]:
        raise ValueError("already_undone")
    merged_id = row["merged_team_id"]
    conn.execute(
        text("UPDATE team SET merged_into_id = NULL, status = 'active' WHERE id = :m"),
        {"m": merged_id},
    )
    conn.execute(
        text("UPDATE team_merge SET is_undone = true, undone_at = now(), undone_by = :actor WHERE id = :id"),
        {"actor": actor, "id": merge_id},
    )
    audit.write_audit(
        conn, workspace_id, actor, "team.merge.undo", entity="team",
        entity_id=str(merged_id), after={"merge_id": str(merge_id)},
    )
    return {"merge_id": merge_id, "merged_team_id": merged_id, "undone": True}
