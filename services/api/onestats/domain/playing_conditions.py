"""Playing conditions & historical rules (Phase 4, Stage 4).

Rules a match is played under, configurable per competition, season, grade and match, and
versioned by scope so a change to one season/grade never rewrites another. Every structured
field is **unknown-aware**: ``None`` means "not recorded" and is preserved as such — the resolver
never substitutes a default for an unknown value.

Effective conditions are resolved in priority order **match → grade → season → competition**:
for each field, the most specific scope that has a non-null value wins; if no scope records a
value it stays unknown. ``points`` (the competition points scheme) and ``extra`` are JSONB and
resolve as whole values at the most specific scope that sets them.

Workspace-scoped (RLS); governed by ``competition.manage``; all mutations audited. Callers must
have set the workspace context.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

# Structured scalar fields (nullable = unknown) that resolve field-by-field.
_SCALAR_FIELDS = ("overs_limit", "max_players", "balls_per_over", "innings_per_side", "format")
# JSONB fields that resolve as whole values.
_JSON_FIELDS = ("points", "extra")
_ALL_FIELDS = (*_SCALAR_FIELDS, *_JSON_FIELDS)

_COLS = (
    "id, workspace_id, scope, competition_id, season_id, grade_id, match_id, "
    "overs_limit, max_players, balls_per_over, innings_per_side, format, points, extra, "
    "notes, source_system, source_ref, created_at, updated_at"
)

_SCOPE_FK = {
    "competition": "competition_id",
    "season": "season_id",
    "grade": "grade_id",
    "match": "match_id",
}
# The real tables a scope target must exist in (match has no table yet).
_SCOPE_TABLE = {"competition": "competition", "season": "season", "grade": "grade"}


def _row(conn: Connection, condition_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(
        text(f"SELECT {_COLS} FROM playing_condition WHERE id = :id"), {"id": condition_id}
    ).mappings().first()
    return dict(r) if r else None


def get_for_scope(conn: Connection, scope: str, target_id: UUID) -> dict[str, Any] | None:
    """The single condition row defined directly at ``scope`` for ``target_id`` (not resolved)."""
    if scope not in _SCOPE_FK:
        raise ValueError("invalid_scope")
    fk = _SCOPE_FK[scope]
    r = conn.execute(
        text(f"SELECT {_COLS} FROM playing_condition WHERE scope = :s AND {fk} = :t"),
        {"s": scope, "t": target_id},
    ).mappings().first()
    return dict(r) if r else None


def set_conditions(
    conn: Connection, workspace_id: UUID, actor: str, *, scope: str, target_id: UUID,
    overs_limit: int | None = None, max_players: int | None = None, balls_per_over: int | None = None,
    innings_per_side: int | None = None, format: str | None = None,
    points: dict[str, Any] | None = None, extra: dict[str, Any] | None = None,
    notes: str | None = None, source_system: str | None = None, source_ref: str | None = None,
) -> dict[str, Any]:
    """Create or update (upsert) the conditions at a single scope target. A field left as ``None``
    is stored as unknown — this never invents a value. The target must exist in this workspace."""
    if scope not in _SCOPE_FK:
        raise ValueError("invalid_scope")
    if scope in _SCOPE_TABLE and conn.execute(
        text(f"SELECT 1 FROM {_SCOPE_TABLE[scope]} WHERE id = :t"), {"t": target_id}
    ).first() is None:
        raise ValueError(f"{scope}_not_found")
    fk = _SCOPE_FK[scope]
    existing = get_for_scope(conn, scope, target_id)
    params = {
        "w": workspace_id, "s": scope, "t": target_id,
        "overs_limit": overs_limit, "max_players": max_players, "balls_per_over": balls_per_over,
        "innings_per_side": innings_per_side, "format": format,
        "points": _json(points), "extra": _json(extra) if extra is not None else None,
        "notes": notes, "ss": source_system, "sr": source_ref,
    }
    if existing is None:
        extra_val = "coalesce(CAST(:extra AS jsonb), '{}'::jsonb)"
        cond_id = conn.execute(
            text(
                f"INSERT INTO playing_condition"
                f"(workspace_id, scope, {fk}, overs_limit, max_players, balls_per_over, "
                f" innings_per_side, format, points, extra, notes, source_system, source_ref) "
                f"VALUES (:w, :s, :t, :overs_limit, :max_players, :balls_per_over, "
                f" :innings_per_side, :format, CAST(:points AS jsonb), {extra_val}, :notes, :ss, :sr) "
                f"RETURNING id"
            ),
            params,
        ).scalar_one()
        action = "playing_condition.create"
    else:
        # Update only the fields provided (None here means "leave as-is" on update, so an existing
        # value is not wiped); use explicit clear_* via the API when a value must be unset.
        cond_id = existing["id"]
        sets, upd = [], {"id": cond_id}
        for field in _SCALAR_FIELDS:
            val = params[field]
            if val is not None:
                sets.append(f"{field} = :{field}")
                upd[field] = val
        if points is not None:
            sets.append("points = CAST(:points AS jsonb)")
            upd["points"] = _json(points)
        if extra is not None:
            sets.append("extra = CAST(:extra AS jsonb)")
            upd["extra"] = _json(extra)
        if notes is not None:
            sets.append("notes = :notes")
            upd["notes"] = notes
        sets.append("updated_at = now()")
        conn.execute(text(f"UPDATE playing_condition SET {', '.join(sets)} WHERE id = :id"), upd)
        action = "playing_condition.update"

    after = _row(conn, cond_id)
    audit.write_audit(
        conn, workspace_id, actor, action, entity="playing_condition", entity_id=str(cond_id),
        before=existing, after=after,
    )
    return after


def clear_conditions(conn: Connection, workspace_id: UUID, actor: str, *, scope: str, target_id: UUID) -> bool:
    """Remove the condition row at a scope target (rules become unknown again at that scope)."""
    existing = get_for_scope(conn, scope, target_id)
    if existing is None:
        return False
    conn.execute(text("DELETE FROM playing_condition WHERE id = :id"), {"id": existing["id"]})
    audit.write_audit(
        conn, workspace_id, actor, "playing_condition.delete", entity="playing_condition",
        entity_id=str(existing["id"]), before=existing,
    )
    return True


def resolve_effective(
    conn: Connection, *, competition_id: UUID | None = None, season_id: UUID | None = None,
    grade_id: UUID | None = None, match_id: UUID | None = None,
) -> dict[str, Any]:
    """Resolve effective conditions in priority order match → grade → season → competition.

    For each structured field the most specific scope with a non-null value wins; JSONB fields
    (``points``/``extra``) take the whole value from the most specific scope that sets them. A
    field no scope records stays ``None`` (unknown). ``sources`` reports which scope supplied each
    resolved field, for transparency.
    """
    layers: list[tuple[str, dict[str, Any] | None]] = [
        ("match", get_for_scope(conn, "match", match_id) if match_id else None),
        ("grade", get_for_scope(conn, "grade", grade_id) if grade_id else None),
        ("season", get_for_scope(conn, "season", season_id) if season_id else None),
        ("competition", get_for_scope(conn, "competition", competition_id) if competition_id else None),
    ]
    resolved: dict[str, Any] = {f: None for f in _ALL_FIELDS}
    sources: dict[str, str | None] = {f: None for f in _ALL_FIELDS}
    for scope_name, row in layers:
        if row is None:
            continue
        for field in _ALL_FIELDS:
            if resolved[field] is None and row.get(field) is not None:
                # extra defaults to {} at the DB; treat an empty object as "not set" for resolution.
                if field == "extra" and row[field] in ({}, None):
                    continue
                resolved[field] = row[field]
                sources[field] = scope_name
    return {"conditions": resolved, "sources": sources}


def list_conditions(conn: Connection, *, competition_id: UUID | None = None) -> list[dict[str, Any]]:
    sql = f"SELECT {_COLS} FROM playing_condition"
    params: dict[str, Any] = {}
    if competition_id is not None:
        # competition-scoped rows, plus season/grade rows under that competition.
        sql += (
            " WHERE competition_id = :c "
            " OR season_id IN (SELECT id FROM season WHERE competition_id = :c) "
            " OR grade_id IN (SELECT id FROM grade WHERE competition_id = :c)"
        )
        params["c"] = competition_id
    sql += " ORDER BY scope, created_at"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def _json(value: dict[str, Any] | None) -> str | None:
    import json
    return None if value is None else json.dumps(value)
