"""Workspace-configurable match formats (Phase 7, Stage 7.5).

Each workspace enables/disables formats and nominates a default; only enabled formats are offered in
the Match Format dropdown. The match's ``format`` is free text, so disabling a format never affects
matches already using it — historical, imported and manually-overridden formats are preserved and
still displayed. Match format is separate from the statistical classification. Workspace-scoped
(FORCE RLS); governed by ``workspace.manage``; audited.
"""
from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

# the standard starting set every workspace is seeded with (all enabled, no default until chosen)
STANDARD_FORMATS: tuple[tuple[str, str], ...] = (
    ("test", "Test"),
    ("first_class", "First-Class"),
    ("odi", "One Day International (ODI)"),
    ("list_a", "List A"),
    ("t20i", "Twenty20 International (T20I)"),
    ("t20", "Twenty20 (T20)"),
    ("two_day", "Two-Day"),
    ("one_day", "One-Day / Limited Overs"),
    ("multi_day", "Multi-Day"),
    ("other", "Other / Custom"),
)

_COLS = "id, code, label, enabled, is_default, is_custom, sort_order"


def ensure_defaults(conn: Connection, workspace_id: UUID) -> None:
    """Seed the standard formats for a workspace the first time they're needed. Idempotent."""
    has_any = conn.execute(
        text("SELECT 1 FROM match_format WHERE workspace_id = :w LIMIT 1"), {"w": workspace_id}
    ).first()
    if has_any:
        return
    for order, (code, label) in enumerate(STANDARD_FORMATS):
        conn.execute(
            text("INSERT INTO match_format(workspace_id, code, label, sort_order) "
                 "VALUES (:w, :c, :l, :o) ON CONFLICT ON CONSTRAINT uq_match_format_code DO NOTHING"),
            {"w": workspace_id, "c": code, "l": label, "o": order},
        )


def list_formats(conn: Connection, workspace_id: UUID, *, enabled_only: bool = False) -> list[dict[str, Any]]:
    ensure_defaults(conn, workspace_id)
    sql = f"SELECT {_COLS} FROM match_format WHERE workspace_id = :w"
    if enabled_only:
        sql += " AND enabled = true"
    sql += " ORDER BY sort_order, label"
    return [dict(r) for r in conn.execute(text(sql), {"w": workspace_id}).mappings().all()]


def _get(conn: Connection, workspace_id: UUID, format_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text(f"SELECT {_COLS} FROM match_format WHERE id = :id AND workspace_id = :w"),
                     {"id": format_id, "w": workspace_id}).mappings().first()
    return dict(r) if r else None


def set_enabled(conn: Connection, workspace_id: UUID, actor: str, format_id: UUID, enabled: bool) -> dict[str, Any]:
    row = _get(conn, workspace_id, format_id)
    if row is None:
        raise ValueError("format_not_found")
    # disabling the default clears the default flag (so no disabled format stays the default)
    conn.execute(
        text("UPDATE match_format SET enabled = :e, is_default = (is_default AND :e) WHERE id = :id"),
        {"e": enabled, "id": format_id},
    )
    audit.write_audit(conn, workspace_id, actor, "match_format.enable", entity="match_format",
                      entity_id=str(format_id), after={"enabled": enabled})
    return _get(conn, workspace_id, format_id)  # type: ignore[return-value]


def set_default(conn: Connection, workspace_id: UUID, actor: str, format_id: UUID) -> dict[str, Any]:
    row = _get(conn, workspace_id, format_id)
    if row is None:
        raise ValueError("format_not_found")
    if not row["enabled"]:
        raise ValueError("cannot_default_disabled_format")
    conn.execute(text("UPDATE match_format SET is_default = false WHERE workspace_id = :w AND is_default"),
                 {"w": workspace_id})
    conn.execute(text("UPDATE match_format SET is_default = true WHERE id = :id"), {"id": format_id})
    audit.write_audit(conn, workspace_id, actor, "match_format.default", entity="match_format",
                      entity_id=str(format_id))
    return _get(conn, workspace_id, format_id)  # type: ignore[return-value]


def create_custom(conn: Connection, workspace_id: UUID, actor: str, label: str) -> dict[str, Any]:
    label = (label or "").strip()
    if not label:
        raise ValueError("missing_label")
    base = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "custom"
    code = base
    n = 1
    while conn.execute(text("SELECT 1 FROM match_format WHERE workspace_id = :w AND code = :c"),
                       {"w": workspace_id, "c": code}).first() is not None:
        n += 1
        code = f"{base}_{n}"
    order = (conn.execute(text("SELECT coalesce(max(sort_order), 0) + 1 FROM match_format WHERE workspace_id = :w"),
                          {"w": workspace_id}).scalar_one())
    fid = conn.execute(
        text("INSERT INTO match_format(workspace_id, code, label, is_custom, sort_order) "
             "VALUES (:w, :c, :l, true, :o) RETURNING id"),
        {"w": workspace_id, "c": code, "l": label, "o": order},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "match_format.create", entity="match_format",
                      entity_id=str(fid), after={"label": label, "code": code})
    return _get(conn, workspace_id, fid)  # type: ignore[return-value]


def default_format_label(conn: Connection, workspace_id: UUID) -> str | None:
    """The enabled default format's label, for defaulting a new match's format. None if unset."""
    ensure_defaults(conn, workspace_id)
    return conn.execute(
        text("SELECT label FROM match_format WHERE workspace_id = :w AND is_default AND enabled LIMIT 1"),
        {"w": workspace_id},
    ).scalar_one_or_none()
