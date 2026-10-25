"""AutoSync source registry (Phase 9, Stage 9.2).

A workspace's configured sources (``sync_source``): which connector, its declared coverage/formats,
reliability/health and last successful access. Credentials are never stored here — only a reference to
secure storage. CRUD + health updates; workspace-scoped (FORCE RLS enforces isolation).
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

RELIABILITY = ("unknown", "ok", "degraded", "down")


def _j(v: Any) -> str | None:
    return None if v is None else json.dumps(v)


def register_source(
    conn: Connection, workspace_id: UUID, actor: str, *, connector_id: str, name: str,
    provider: str | None = None, access_method: str | None = None, endpoint: str | None = None,
    auth_required: bool = False, credentials_ref: str | None = None, countries: Any = None,
    formats: Any = None, coverage: Any = None, rate_limit: Any = None, connector_version: str | None = None,
    mapping: Any = None, enabled: bool = True, notes: str | None = None,
) -> dict[str, Any]:
    """Add a source to the workspace. Unique on name (per workspace)."""
    existing = conn.execute(
        text("SELECT id FROM sync_source WHERE workspace_id = :w AND name = :n"),
        {"w": workspace_id, "n": name},
    ).scalar_one_or_none()
    if existing is not None:
        raise ValueError("source_name_exists")
    sid = conn.execute(
        text("INSERT INTO sync_source(workspace_id, connector_id, name, provider, access_method, endpoint, "
             "auth_required, credentials_ref, countries, formats, coverage, rate_limit, connector_version, "
             "mapping, enabled, notes) VALUES (:w, :cid, :n, :pv, :am, :ep, :auth, :cr, CAST(:co AS jsonb), "
             "CAST(:fm AS jsonb), CAST(:cv AS jsonb), CAST(:rl AS jsonb), :ver, CAST(:mp AS jsonb), :en, :nt) "
             "RETURNING id"),
        {"w": workspace_id, "cid": connector_id, "n": name, "pv": provider, "am": access_method, "ep": endpoint,
         "auth": auth_required, "cr": credentials_ref, "co": _j(countries), "fm": _j(formats), "cv": _j(coverage),
         "rl": _j(rate_limit), "ver": connector_version, "mp": _j(mapping), "en": enabled, "nt": notes},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "autosync.source_registered", entity="sync_source",
                      entity_id=str(sid), after={"connector_id": connector_id, "name": name})
    return get_source(conn, sid)


def get_source(conn: Connection, source_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text("SELECT * FROM sync_source WHERE id = :id"), {"id": source_id}).mappings().first()
    return dict(r) if r else None


def list_sources(conn: Connection, workspace_id: UUID, *, enabled_only: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM sync_source WHERE workspace_id = :w"
    if enabled_only:
        sql += " AND enabled = true"
    sql += " ORDER BY name"
    return [dict(r) for r in conn.execute(text(sql), {"w": workspace_id}).mappings().all()]


def set_enabled(conn: Connection, workspace_id: UUID, actor: str, source_id: UUID, enabled: bool) -> dict[str, Any]:
    conn.execute(text("UPDATE sync_source SET enabled = :e, updated_at = now() WHERE id = :id"),
                 {"e": enabled, "id": source_id})
    audit.write_audit(conn, workspace_id, actor, "autosync.source_enabled", entity="sync_source",
                      entity_id=str(source_id), after={"enabled": enabled})
    return get_source(conn, source_id)


def record_success(conn: Connection, source_id: UUID) -> None:
    """Mark a successful access (health = ok, last_success_at = now)."""
    conn.execute(text("UPDATE sync_source SET reliability = 'ok', last_success_at = now(), updated_at = now() "
                      "WHERE id = :id"), {"id": source_id})


def record_health(conn: Connection, workspace_id: UUID, actor: str, source_id: UUID, *,
                  reliability: str, notes: str | None = None) -> dict[str, Any]:
    """Record a health signal (degraded/down/ok). A failed access is a health signal, NOT evidence
    that no matches exist."""
    if reliability not in RELIABILITY:
        raise ValueError("invalid_reliability")
    conn.execute(text("UPDATE sync_source SET reliability = :r, notes = COALESCE(:n, notes), updated_at = now() "
                      "WHERE id = :id"), {"r": reliability, "n": notes, "id": source_id})
    audit.write_audit(conn, workspace_id, actor, "autosync.source_health", entity="sync_source",
                      entity_id=str(source_id), after={"reliability": reliability})
    return get_source(conn, source_id)
