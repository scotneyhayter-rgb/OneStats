"""Workspace branding service (deliverable 9).

Stores validated brand colours, theme mode, logo reference, tagline and presets per
workspace, and resolves accessible (WCAG 2.2 AA) foreground colours with warnings. All
writes are workspace-scoped (RLS) and audited by the caller's context. Workspace branding
personalises an organisation's experience; it never replaces the OneStats product identity.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.core import color
from onestats.domain import audit

COLOUR_FIELDS = (
    "primary_colour",
    "secondary_colour",
    "third_colour",
    "fourth_colour",
    "accent_colour",
)
_THEME_MODES = {"light", "dark", "system"}
_COLS = (
    "workspace_id, primary_colour, secondary_colour, third_colour, fourth_colour, "
    "accent_colour, theme_mode, background, logo_ref, alt_logos, tagline, presets, updated_at"
)


def get_branding(conn: Connection, workspace_id: UUID) -> dict[str, Any] | None:
    row = conn.execute(
        text(f"SELECT {_COLS} FROM branding WHERE workspace_id = :w"), {"w": workspace_id}
    ).mappings().first()
    return dict(row) if row else None


def _validate(fields: dict[str, Any]) -> None:
    for key in COLOUR_FIELDS:
        val = fields.get(key)
        if val is not None and not color.is_valid_hex(val):
            raise ValueError(f"invalid_colour:{key}")
    tm = fields.get("theme_mode")
    if tm is not None and tm not in _THEME_MODES:
        raise ValueError("invalid_theme_mode")


def set_branding(
    conn: Connection, workspace_id: UUID, actor_user_id: UUID, fields: dict[str, Any]
) -> dict[str, Any]:
    _validate(fields)
    before = get_branding(conn, workspace_id)
    merged: dict[str, Any] = dict(before or {})
    merged.pop("updated_at", None)
    merged.pop("workspace_id", None)
    for k, v in fields.items():
        merged[k] = v
    params = {
        "w": workspace_id,
        "primary": merged.get("primary_colour"),
        "secondary": merged.get("secondary_colour"),
        "third": merged.get("third_colour"),
        "fourth": merged.get("fourth_colour"),
        "accent": merged.get("accent_colour"),
        "theme": merged.get("theme_mode") or "system",
        "background": json.dumps(merged.get("background")) if merged.get("background") is not None else None,
        "logo": merged.get("logo_ref"),
        "alt": json.dumps(merged.get("alt_logos")) if merged.get("alt_logos") is not None else None,
        "tagline": merged.get("tagline"),
        "presets": json.dumps(merged.get("presets")) if merged.get("presets") is not None else None,
    }
    conn.execute(
        text(
            "INSERT INTO branding(workspace_id, primary_colour, secondary_colour, "
            "third_colour, fourth_colour, accent_colour, theme_mode, background, logo_ref, "
            "alt_logos, tagline, presets, updated_at) VALUES (:w, :primary, :secondary, "
            ":third, :fourth, :accent, :theme, CAST(:background AS jsonb), :logo, "
            "CAST(:alt AS jsonb), :tagline, CAST(:presets AS jsonb), now()) "
            "ON CONFLICT (workspace_id) DO UPDATE SET "
            "primary_colour=EXCLUDED.primary_colour, secondary_colour=EXCLUDED.secondary_colour, "
            "third_colour=EXCLUDED.third_colour, fourth_colour=EXCLUDED.fourth_colour, "
            "accent_colour=EXCLUDED.accent_colour, theme_mode=EXCLUDED.theme_mode, "
            "background=EXCLUDED.background, logo_ref=EXCLUDED.logo_ref, "
            "alt_logos=EXCLUDED.alt_logos, tagline=EXCLUDED.tagline, presets=EXCLUDED.presets, "
            "updated_at=now()"
        ),
        params,
    )
    after = get_branding(conn, workspace_id)
    audit.write_audit(
        conn, workspace_id, str(actor_user_id), "branding.update", entity="branding",
        entity_id=str(workspace_id),
        before={k: before.get(k) for k in COLOUR_FIELDS} if before else None,
        after={k: after.get(k) for k in COLOUR_FIELDS},
    )
    return after


def reset_branding(conn: Connection, workspace_id: UUID, actor_user_id: UUID) -> None:
    conn.execute(text("DELETE FROM branding WHERE workspace_id = :w"), {"w": workspace_id})
    audit.write_audit(
        conn, workspace_id, str(actor_user_id), "branding.reset",
        entity="branding", entity_id=str(workspace_id),
    )


def resolve_tokens(branding: dict[str, Any] | None) -> dict[str, Any]:
    """Resolve accessible foregrounds for each configured colour, with AA warnings."""
    result: dict[str, Any] = {"colours": {}, "warnings": []}
    if not branding:
        result["theme_mode"] = "system"
        return result
    result["theme_mode"] = branding.get("theme_mode") or "system"
    for key in COLOUR_FIELDS:
        val = branding.get(key)
        if val and color.is_valid_hex(val):
            res = color.resolve(val)
            result["colours"][key] = res
            if not res["meets_aa"]:
                result["warnings"].append(
                    f"{key} ({val}) cannot reach WCAG AA (4.5:1) with black or white text"
                )
    return result


def published_payload(workspace_id: UUID, branding: dict[str, Any] | None) -> dict[str, Any]:
    """Public-safe branding payload for the desktop/published interfaces."""
    resolved = resolve_tokens(branding)
    return {
        "workspace_id": str(workspace_id),
        "theme_mode": resolved["theme_mode"],
        "colours": resolved["colours"],
        "logo_ref": (branding or {}).get("logo_ref"),
        "tagline": (branding or {}).get("tagline"),
    }
