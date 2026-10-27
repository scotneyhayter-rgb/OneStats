"""Competitions, divisions, grades, seasons & entries (Phase 4, Stage 3).

Models the competition structure a club's teams play in, over time:

* Competitions may be owned by an association (organisation) or operate independently.
* Renames are preserved (``competition_name_history``/``grade_name_history``) and external
  provenance recorded — current arrangements never overwrite historical information.
* Seasons may span two calendar years and reach back to 1919; date precision may be unknown
  (nullable), and unknown stays unknown rather than being invented.
* ``team_grade_entry`` places a team in a grade for a season; the same team can take different
  grades across seasons, several teams from one club can share a grade, and a team can appear in
  several competitions. Duplicate entries are prevented by a unique constraint (idempotent).
* ``match_classification`` is a preparatory, unknown-aware vocabulary for later match phases;
  unmapped Cricket Statz source values are preserved as ``unresolved`` rather than guessed (D32).

All operations are workspace-scoped (RLS) and audited. Callers must have set the workspace
context so RLS scopes reads and writes to the one workspace.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

_COMP_COLS = (
    "id, workspace_id, name, short_name, association_id, status, notes, season_model, "
    "source_system, source_ref, created_at"
)
SEASON_MODELS = ("au_summer", "calendar", "uk_summer", "custom", "unknown")

# Documented, source-independent finals/home-and-away vocabulary. A round label alone never
# proves a finals classification, so these are generic concepts an administrator opts into; raw
# source codes are mapped only when verified (otherwise kept unresolved).
DEFAULT_CLASSIFICATIONS = (
    ("home_away", "Home-and-away", False),
    ("final", "Final", True),
    ("semi_final", "Semi-final", True),
    ("preliminary_final", "Preliminary final", True),
    ("grand_final", "Grand final", True),
    ("other", "Other", None),
)


def _normalise(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


# --------------------------------------------------------------------------- competitions


def get_competition(conn: Connection, competition_id: UUID) -> dict[str, Any] | None:
    row = conn.execute(
        text(f"SELECT {_COMP_COLS} FROM competition WHERE id = :id"), {"id": competition_id}
    ).mappings().first()
    return dict(row) if row else None


def list_competitions(
    conn: Connection, *, association_id: UUID | None = None, search: str | None = None
) -> list[dict[str, Any]]:
    sql = f"SELECT {_COMP_COLS} FROM competition"
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if association_id is not None:
        clauses.append("association_id = :assoc")
        params["assoc"] = association_id
    if search:
        clauses.append("name ILIKE :q")
        params["q"] = f"%{search}%"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY name"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def create_competition(
    conn: Connection, workspace_id: UUID, actor: str,
    *, name: str, short_name: str | None = None, association_id: UUID | None = None,
    notes: str | None = None, season_model: str = "unknown",
    source_system: str | None = None, source_ref: str | None = None,
) -> UUID:
    if season_model not in SEASON_MODELS:
        raise ValueError("invalid_season_model")
    name = (name or "").strip()
    if not name:
        raise ValueError("missing_name")
    if association_id is not None and conn.execute(
        text("SELECT 1 FROM organisation WHERE id = :o"), {"o": association_id}
    ).first() is None:
        raise ValueError("association_not_found")
    comp_id = conn.execute(
        text(
            "INSERT INTO competition"
            "(workspace_id, name, short_name, association_id, notes, season_model, source_system, source_ref) "
            "VALUES (:w, :n, :sn, :assoc, :notes, :sm, :ss, :sr) RETURNING id"
        ),
        {"w": workspace_id, "n": name, "sn": short_name, "assoc": association_id,
         "notes": notes, "sm": season_model, "ss": source_system, "sr": source_ref},
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO competition_name_history(workspace_id, competition_id, name, note) "
            "VALUES (:w, :o, :n, 'initial name')"
        ),
        {"w": workspace_id, "o": comp_id, "n": name},
    )
    if source_system and source_ref:
        add_source_identity(conn, workspace_id, actor, comp_id,
                            source_system=source_system, source_ref=source_ref,
                            source_display_name=name, _audit=False)
    audit.write_audit(
        conn, workspace_id, actor, "competition.create", entity="competition",
        entity_id=str(comp_id),
        after={"name": name, "association_id": str(association_id) if association_id else None},
    )
    return comp_id


def update_competition(
    conn: Connection, workspace_id: UUID, actor: str, competition_id: UUID,
    *, name: str | None = None, short_name: str | None = None, status: str | None = None,
    association_id: UUID | None = None, clear_association: bool = False, notes: str | None = None,
    name_change_note: str | None = None, season_model: str | None = None,
) -> dict[str, Any]:
    before = get_competition(conn, competition_id)
    if before is None:
        raise ValueError("competition_not_found")
    if season_model is not None and season_model not in SEASON_MODELS:
        raise ValueError("invalid_season_model")
    new_name = name.strip() if name is not None else None
    if name is not None and not new_name:
        raise ValueError("missing_name")
    if association_id is not None and conn.execute(
        text("SELECT 1 FROM organisation WHERE id = :o"), {"o": association_id}
    ).first() is None:
        raise ValueError("association_not_found")
    # clear_association lets an owned competition become independent explicitly.
    assoc_sql = "association_id = :assoc" if (association_id is not None or clear_association) else \
                "association_id = association_id"
    conn.execute(
        text(
            f"UPDATE competition SET name = coalesce(:n, name), "
            f"short_name = coalesce(:sn, short_name), status = coalesce(:st, status), "
            f"notes = coalesce(:notes, notes), season_model = coalesce(:smodel, season_model), "
            f"{assoc_sql} WHERE id = :id"
        ),
        {"n": new_name, "sn": short_name, "st": status, "notes": notes, "smodel": season_model,
         "assoc": None if clear_association else association_id, "id": competition_id},
    )
    if new_name and new_name != before["name"]:
        conn.execute(
            text(
                "INSERT INTO competition_name_history(workspace_id, competition_id, name, note) "
                "VALUES (:w, :o, :n, :note)"
            ),
            {"w": workspace_id, "o": competition_id, "n": new_name, "note": name_change_note or "renamed"},
        )
    after = get_competition(conn, competition_id)
    audit.write_audit(
        conn, workspace_id, actor, "competition.update", entity="competition",
        entity_id=str(competition_id), before=before, after=after,
    )
    return after


def delete_competition(conn: Connection, workspace_id: UUID, actor: str, competition_id: UUID) -> None:
    """Delete a competition. Refuses if any matches reference it (to protect match data and
    competition-scoped statistics) — those must be reassigned or removed first. For a competition
    with no matches, its grades/seasons/divisions and name history are removed with it. Audited."""
    before = get_competition(conn, competition_id)
    if before is None:
        raise ValueError("competition_not_found")
    n_matches = conn.execute(
        text("SELECT count(*) FROM match WHERE competition_id = :c"), {"c": competition_id}
    ).scalar() or 0
    if n_matches:
        raise ValueError(f"competition_has_matches:{n_matches}")
    # grade / season / division (and team entries via grade) are ON DELETE CASCADE from competition;
    # match / affiliation links are SET NULL. Remove name history explicitly, then the competition.
    conn.execute(text("DELETE FROM competition_name_history WHERE competition_id = :c"), {"c": competition_id})
    conn.execute(text("DELETE FROM competition WHERE id = :c AND workspace_id = :w"),
                 {"c": competition_id, "w": workspace_id})
    audit.write_audit(
        conn, workspace_id, actor, "competition.delete", entity="competition",
        entity_id=str(competition_id), before=before, after=None,
    )


def list_name_history(conn: Connection, competition_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT id, name, valid_from, valid_to, note, created_at "
            "FROM competition_name_history WHERE competition_id = :o "
            "ORDER BY valid_from NULLS FIRST, created_at"
        ),
        {"o": competition_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def name_as_of(conn: Connection, competition_id: UUID, on_date: Any) -> str | None:
    row = conn.execute(
        text(
            "SELECT name FROM competition_name_history WHERE competition_id = :o "
            "AND (valid_from IS NULL OR valid_from <= :d) AND (valid_to IS NULL OR valid_to >= :d) "
            "ORDER BY valid_from DESC NULLS LAST, created_at DESC LIMIT 1"
        ),
        {"o": competition_id, "d": on_date},
    ).scalar_one_or_none()
    if row is not None:
        return row
    return conn.execute(
        text(
            "SELECT name FROM competition_name_history WHERE competition_id = :o "
            "ORDER BY valid_from NULLS FIRST, created_at LIMIT 1"
        ),
        {"o": competition_id},
    ).scalar_one_or_none()


def add_source_identity(
    conn: Connection, workspace_id: UUID, actor: str, competition_id: UUID,
    *, source_system: str, source_ref: str, source_display_name: str | None = None, _audit: bool = True,
) -> dict[str, Any]:
    if not source_system or not source_ref:
        raise ValueError("missing_source_ref")
    existing = conn.execute(
        text(
            "SELECT id, competition_id, source_system, source_ref, source_display_name "
            "FROM competition_source_identity WHERE source_system = :ss AND source_ref = :sr"
        ),
        {"ss": source_system, "sr": source_ref},
    ).mappings().first()
    if existing is not None:
        return dict(existing) | {"created": False}
    row = conn.execute(
        text(
            "INSERT INTO competition_source_identity"
            "(workspace_id, competition_id, source_system, source_ref, source_display_name) "
            "VALUES (:w, :o, :ss, :sr, :dn) "
            "RETURNING id, competition_id, source_system, source_ref, source_display_name"
        ),
        {"w": workspace_id, "o": competition_id, "ss": source_system, "sr": source_ref, "dn": source_display_name},
    ).mappings().one()
    if _audit:
        audit.write_audit(
            conn, workspace_id, actor, "competition.source_identity.add", entity="competition",
            entity_id=str(competition_id), after={"source_system": source_system, "source_ref": source_ref},
        )
    return dict(row) | {"created": True}


def find_duplicate_candidates(conn: Connection, competition_id: UUID) -> list[dict[str, Any]]:
    """Suggest possible duplicate competitions (identical normalised name) for human review.
    Advisory only; never merges."""
    comp = get_competition(conn, competition_id)
    if comp is None:
        raise ValueError("competition_not_found")
    key = _normalise(comp["name"])
    rows = conn.execute(
        text(
            "SELECT id, name FROM competition WHERE id <> :o "
            "AND regexp_replace(lower(btrim(name)), '\\s+', ' ', 'g') = :k ORDER BY name"
        ),
        {"o": competition_id, "k": key},
    ).mappings().all()
    return [{"competition_id": r["id"], "name": r["name"], "evidence": ["same_normalised_name"],
             "confidence": "weak"} for r in rows]


# --------------------------------------------------------------------------- divisions


def create_division(
    conn: Connection, workspace_id: UUID, actor: str, competition_id: UUID,
    *, name: str, source_system: str | None = None, source_ref: str | None = None,
) -> UUID:
    name = (name or "").strip()
    if not name:
        raise ValueError("missing_name")
    if get_competition(conn, competition_id) is None:
        raise ValueError("competition_not_found")
    div_id = conn.execute(
        text(
            "INSERT INTO division(workspace_id, competition_id, name, source_system, source_ref) "
            "VALUES (:w, :c, :n, :ss, :sr) RETURNING id"
        ),
        {"w": workspace_id, "c": competition_id, "n": name, "ss": source_system, "sr": source_ref},
    ).scalar_one()
    audit.write_audit(
        conn, workspace_id, actor, "division.create", entity="division",
        entity_id=str(div_id), after={"name": name, "competition_id": str(competition_id)},
    )
    return div_id


def list_divisions(conn: Connection, competition_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT id, name, status, source_system, source_ref, created_at "
            "FROM division WHERE competition_id = :c ORDER BY name"
        ),
        {"c": competition_id},
    ).mappings().all()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- grades


def create_grade(
    conn: Connection, workspace_id: UUID, actor: str, competition_id: UUID,
    *, name: str, program: str | None = None, division_id: UUID | None = None,
    notes: str | None = None, source_system: str | None = None, source_ref: str | None = None,
) -> UUID:
    name = (name or "").strip()
    if not name:
        raise ValueError("missing_name")
    if get_competition(conn, competition_id) is None:
        raise ValueError("competition_not_found")
    if division_id is not None and conn.execute(
        text("SELECT 1 FROM division WHERE id = :d AND competition_id = :c"),
        {"d": division_id, "c": competition_id},
    ).first() is None:
        raise ValueError("division_not_found")
    grade_id = conn.execute(
        text(
            "INSERT INTO grade"
            "(workspace_id, competition_id, division_id, name, program, notes, source_system, source_ref) "
            "VALUES (:w, :c, :d, :n, :p, :notes, :ss, :sr) RETURNING id"
        ),
        {"w": workspace_id, "c": competition_id, "d": division_id, "n": name, "p": program,
         "notes": notes, "ss": source_system, "sr": source_ref},
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO grade_name_history(workspace_id, grade_id, name, note) "
            "VALUES (:w, :o, :n, 'initial name')"
        ),
        {"w": workspace_id, "o": grade_id, "n": name},
    )
    audit.write_audit(
        conn, workspace_id, actor, "grade.create", entity="grade",
        entity_id=str(grade_id), after={"name": name, "competition_id": str(competition_id), "program": program},
    )
    return grade_id


def rename_grade(
    conn: Connection, workspace_id: UUID, actor: str, grade_id: UUID, *, name: str,
    name_change_note: str | None = None,
) -> dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise ValueError("missing_name")
    before = conn.execute(
        text("SELECT id, name FROM grade WHERE id = :id"), {"id": grade_id}
    ).mappings().first()
    if before is None:
        raise ValueError("grade_not_found")
    if name != before["name"]:
        conn.execute(text("UPDATE grade SET name = :n WHERE id = :id"), {"n": name, "id": grade_id})
        conn.execute(
            text(
                "INSERT INTO grade_name_history(workspace_id, grade_id, name, note) "
                "VALUES (:w, :o, :n, :note)"
            ),
            {"w": workspace_id, "o": grade_id, "n": name, "note": name_change_note or "renamed"},
        )
        audit.write_audit(
            conn, workspace_id, actor, "grade.rename", entity="grade",
            entity_id=str(grade_id), before=dict(before), after={"name": name},
        )
    return {"id": grade_id, "name": name}


def list_grades(conn: Connection, competition_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT id, competition_id, division_id, name, program, status, source_system, source_ref, created_at "
            "FROM grade WHERE competition_id = :c ORDER BY name"
        ),
        {"c": competition_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def grade_name_as_of(conn: Connection, grade_id: UUID, on_date: Any) -> str | None:
    row = conn.execute(
        text(
            "SELECT name FROM grade_name_history WHERE grade_id = :o "
            "AND (valid_from IS NULL OR valid_from <= :d) AND (valid_to IS NULL OR valid_to >= :d) "
            "ORDER BY valid_from DESC NULLS LAST, created_at DESC LIMIT 1"
        ),
        {"o": grade_id, "d": on_date},
    ).scalar_one_or_none()
    if row is not None:
        return row
    return conn.execute(
        text(
            "SELECT name FROM grade_name_history WHERE grade_id = :o "
            "ORDER BY valid_from NULLS FIRST, created_at LIMIT 1"
        ),
        {"o": grade_id},
    ).scalar_one_or_none()


def add_grade_name_history(
    conn: Connection, workspace_id: UUID, actor: str, grade_id: UUID,
    *, name: str, valid_from: Any | None = None, valid_to: Any | None = None, note: str | None = None,
) -> UUID:
    name = (name or "").strip()
    if not name:
        raise ValueError("missing_name")
    if conn.execute(text("SELECT 1 FROM grade WHERE id = :id"), {"id": grade_id}).first() is None:
        raise ValueError("grade_not_found")
    hist_id = conn.execute(
        text(
            "INSERT INTO grade_name_history(workspace_id, grade_id, name, valid_from, valid_to, note) "
            "VALUES (:w, :o, :n, :vf, :vt, :note) RETURNING id"
        ),
        {"w": workspace_id, "o": grade_id, "n": name, "vf": valid_from, "vt": valid_to, "note": note},
    ).scalar_one()
    audit.write_audit(
        conn, workspace_id, actor, "grade.name_history.add", entity="grade",
        entity_id=str(grade_id), after={"name": name},
    )
    return hist_id


# --------------------------------------------------------------------------- seasons


def create_season(
    conn: Connection, workspace_id: UUID, actor: str, competition_id: UUID,
    *, label: str, start_date: Any | None = None, end_date: Any | None = None,
    source_system: str | None = None, source_ref: str | None = None,
) -> UUID:
    label = (label or "").strip()
    if not label:
        raise ValueError("missing_label")
    if get_competition(conn, competition_id) is None:
        raise ValueError("competition_not_found")
    if conn.execute(
        text("SELECT 1 FROM season WHERE competition_id = :c AND label = :l"),
        {"c": competition_id, "l": label},
    ).first() is not None:
        raise ValueError("duplicate_season")
    season_id = conn.execute(
        text(
            "INSERT INTO season(workspace_id, competition_id, label, start_date, end_date, source_system, source_ref) "
            "VALUES (:w, :c, :l, :sd, :ed, :ss, :sr) RETURNING id"
        ),
        {"w": workspace_id, "c": competition_id, "l": label, "sd": start_date, "ed": end_date,
         "ss": source_system, "sr": source_ref},
    ).scalar_one()
    audit.write_audit(
        conn, workspace_id, actor, "season.create", entity="season",
        entity_id=str(season_id), after={"label": label, "competition_id": str(competition_id)},
    )
    return season_id


def list_seasons(conn: Connection, competition_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT id, label, start_date, end_date, status, source_system, source_ref, created_at "
            "FROM season WHERE competition_id = :c ORDER BY label"
        ),
        {"c": competition_id},
    ).mappings().all()
    return [dict(r) for r in rows]


# --------------------------------------------------------------- team-grade-season entries


def enter_team(
    conn: Connection, workspace_id: UUID, actor: str,
    *, team_id: UUID, grade_id: UUID, season_id: UUID,
    notes: str | None = None, source_system: str | None = None, source_ref: str | None = None,
) -> dict[str, Any]:
    """Enter a team in a grade for a season. Idempotent: a repeated entry returns the existing
    row (``created=False``) rather than duplicating. Validates team/grade/season all exist in
    this workspace and that the grade and season belong to the same competition."""
    if conn.execute(text("SELECT 1 FROM team WHERE id = :t"), {"t": team_id}).first() is None:
        raise ValueError("team_not_found")
    grade = conn.execute(
        text("SELECT competition_id FROM grade WHERE id = :g"), {"g": grade_id}
    ).mappings().first()
    if grade is None:
        raise ValueError("grade_not_found")
    season = conn.execute(
        text("SELECT competition_id FROM season WHERE id = :s"), {"s": season_id}
    ).mappings().first()
    if season is None:
        raise ValueError("season_not_found")
    if grade["competition_id"] != season["competition_id"]:
        raise ValueError("grade_season_competition_mismatch")
    existing = conn.execute(
        text(
            "SELECT id FROM team_grade_entry "
            "WHERE team_id = :t AND grade_id = :g AND season_id = :s"
        ),
        {"t": team_id, "g": grade_id, "s": season_id},
    ).scalar_one_or_none()
    if existing is not None:
        return {"entry_id": existing, "created": False}
    entry_id = conn.execute(
        text(
            "INSERT INTO team_grade_entry"
            "(workspace_id, team_id, grade_id, season_id, notes, source_system, source_ref) "
            "VALUES (:w, :t, :g, :s, :notes, :ss, :sr) RETURNING id"
        ),
        {"w": workspace_id, "t": team_id, "g": grade_id, "s": season_id,
         "notes": notes, "ss": source_system, "sr": source_ref},
    ).scalar_one()
    audit.write_audit(
        conn, workspace_id, actor, "team_grade_entry.create", entity="team_grade_entry",
        entity_id=str(entry_id),
        after={"team_id": str(team_id), "grade_id": str(grade_id), "season_id": str(season_id)},
    )
    return {"entry_id": entry_id, "created": True}


def list_entries(
    conn: Connection, *, team_id: UUID | None = None, grade_id: UUID | None = None,
    season_id: UUID | None = None,
) -> list[dict[str, Any]]:
    sql = (
        "SELECT id, team_id, grade_id, season_id, notes, source_system, source_ref, created_at "
        "FROM team_grade_entry"
    )
    clauses: list[str] = []
    params: dict[str, Any] = {}
    for col, val in (("team_id", team_id), ("grade_id", grade_id), ("season_id", season_id)):
        if val is not None:
            clauses.append(f"{col} = :{col}")
            params[col] = val
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


# --------------------------------------------------------------- match classifications


def ensure_default_classifications(conn: Connection, workspace_id: UUID, actor: str) -> list[dict[str, Any]]:
    """Create the documented generic finals/home-and-away classifications for a workspace
    (idempotent). These are source-independent concepts an administrator opts into."""
    for key, label, is_final in DEFAULT_CLASSIFICATIONS:
        conn.execute(
            text(
                "INSERT INTO match_classification(workspace_id, key, label, is_final, status) "
                "SELECT :w, :k, :l, :f, 'confirmed' "
                "WHERE NOT EXISTS (SELECT 1 FROM match_classification WHERE key = :k AND status = 'confirmed')"
            ),
            {"w": workspace_id, "k": key, "l": label, "f": is_final},
        )
    audit.write_audit(
        conn, workspace_id, actor, "match_classification.seed_defaults", entity="match_classification",
        after={"count": len(DEFAULT_CLASSIFICATIONS)},
    )
    return list_classifications(conn)


def record_unresolved_classification(
    conn: Connection, workspace_id: UUID, actor: str,
    *, source_value: str, source_system: str | None = None, source_ref: str | None = None,
    notes: str | None = None,
) -> UUID:
    """Preserve a source classification that cannot be confidently mapped. ``is_final`` is left
    NULL (unknown) and ``status='unresolved'`` so it is flagged for later verification, never
    guessed (D32). A round label alone is not treated as proof of a finals classification."""
    source_value = (source_value or "").strip()
    if not source_value:
        raise ValueError("missing_source_value")
    row_id = conn.execute(
        text(
            "INSERT INTO match_classification"
            "(workspace_id, status, unresolved_source_value, source_system, source_ref, notes) "
            "VALUES (:w, 'unresolved', :v, :ss, :sr, :notes) RETURNING id"
        ),
        {"w": workspace_id, "v": source_value, "ss": source_system, "sr": source_ref, "notes": notes},
    ).scalar_one()
    audit.write_audit(
        conn, workspace_id, actor, "match_classification.record_unresolved",
        entity="match_classification", entity_id=str(row_id),
        after={"unresolved_source_value": source_value, "source_system": source_system},
    )
    return row_id


def list_classifications(conn: Connection, *, status: str | None = None) -> list[dict[str, Any]]:
    sql = (
        "SELECT id, key, label, is_final, status, unresolved_source_value, source_system, source_ref, created_at "
        "FROM match_classification"
    )
    params: dict[str, Any] = {}
    if status is not None:
        sql += " WHERE status = :st"
        params["st"] = status
    sql += " ORDER BY status, key NULLS LAST, unresolved_source_value"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]
