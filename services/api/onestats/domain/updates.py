"""Update-system domain services: version/compatibility reporting, maintenance mode, pre-update
checks, backup readiness and the update audit trail.

All functions here are read/administrative only. They never download, execute, or install anything —
the actual desktop/server update *execution* is performed by signed packages and privileged
maintenance tooling outside the ordinary API (see docs/74-update-system.md). This keeps the backend
free of any remote-command-execution surface.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from onestats.core import version as ver
from onestats.core.config import Settings


# --- Schema version ---------------------------------------------------------------------------

def _schema_level(head: str | None) -> int | None:
    if not head:
        return None
    digits = ""
    for ch in head:
        if ch.isdigit():
            digits += ch
        else:
            break
    return int(digits) if digits else None


def current_schema(conn: Connection) -> dict[str, Any]:
    """The database's current Alembic head vs. the head the running server code expects."""
    head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    level = _schema_level(head)
    return {
        "current_head": head,
        "current_level": level,
        "expected_head": ver.DB_SCHEMA_HEAD,
        "expected_level": ver.DB_SCHEMA_LEVEL,
        "up_to_date": head == ver.DB_SCHEMA_HEAD,
        "migration_pending": level is not None and level < ver.DB_SCHEMA_LEVEL,
    }


# --- System state / maintenance mode ----------------------------------------------------------

def get_system_state(conn: Connection) -> dict[str, Any]:
    row = conn.execute(
        text("SELECT maintenance_mode, maintenance_message, maintenance_since, maintenance_by "
             "FROM system_state WHERE id = true")
    ).mappings().first()
    if row is None:
        return {"maintenance_mode": False, "maintenance_message": None, "maintenance_since": None, "maintenance_by": None}
    return dict(row)


# Short-lived cache so the per-request maintenance gate doesn't hit the DB on every write.
_MAINT_CACHE: dict[str, Any] = {"val": False, "ts": 0.0}


def is_maintenance(engine: Engine, ttl: float = 3.0) -> bool:
    """Cached read of the maintenance flag for the request middleware (fails open to False)."""
    now = time.monotonic()
    if now - _MAINT_CACHE["ts"] < ttl:
        return bool(_MAINT_CACHE["val"])
    val = False
    try:
        with engine.begin() as conn:
            val = bool(conn.execute(text("SELECT maintenance_mode FROM system_state WHERE id = true")).scalar())
    except Exception:  # noqa: BLE001 - never block a request on a maintenance-flag read failure
        val = False
    _MAINT_CACHE.update(val=val, ts=now)
    return val


def set_maintenance(conn: Connection, actor: str | None, *, on: bool, message: str | None = None) -> dict[str, Any]:
    _MAINT_CACHE["ts"] = 0.0  # invalidate the gate cache immediately
    conn.execute(
        text("UPDATE system_state SET maintenance_mode = :m, maintenance_message = :msg, "
             "maintenance_since = CASE WHEN :m THEN now() ELSE NULL END, "
             "maintenance_by = CASE WHEN :m THEN :by ELSE NULL END, updated_at = now() WHERE id = true"),
        {"m": on, "msg": message if on else None, "by": actor},
    )
    record_event(conn, component="server",
                 event="maintenance_on" if on else "maintenance_off", actor=actor, outcome="ok",
                 detail={"message": message} if (on and message) else None)
    return get_system_state(conn)


# --- Capability / compatibility ---------------------------------------------------------------

def capability(conn: Connection, settings: Settings) -> dict[str, Any]:
    """The compatibility capability document a desktop client reads to make update decisions.
    Deliberately minimal — no infrastructure details, no secrets."""
    state = get_system_state(conn)
    return {
        "server_version": ver.SERVER_VERSION,
        "api_version": ver.API_VERSION,
        "channel": settings.release_channel,
        "database": current_schema(conn),
        "min_desktop_version": ver.MIN_DESKTOP_VERSION,
        "max_desktop_version": ver.MAX_DESKTOP_VERSION,
        "min_server_for_desktop": ver.MIN_SERVER_FOR_DESKTOP,
        "maintenance": {"mode": bool(state["maintenance_mode"]), "message": state["maintenance_message"]},
    }


def compatibility_for(conn: Connection, desktop_version: str | None) -> dict[str, Any]:
    state = get_system_state(conn)
    return ver.evaluate_compatibility(desktop_version, maintenance=bool(state["maintenance_mode"]))


# --- Pre-update checks & backup readiness ------------------------------------------------------

def _backup_dir(settings: Settings) -> Path:
    base = settings.backup_dir or os.path.join(settings.media_root, "backups")
    return Path(base)


def backup_readiness(settings: Settings) -> dict[str, Any]:
    """Whether a backup destination exists / can be created and how much free space it has.
    Does NOT take a backup — only reports readiness (section 6)."""
    d = _backup_dir(settings)
    writable = False
    free_bytes = None
    try:
        d.mkdir(parents=True, exist_ok=True)
        test = d / ".write-test"
        test.write_text("ok", encoding="utf-8")
        test.unlink()
        writable = True
        free_bytes = shutil.disk_usage(str(d)).free
    except OSError:
        writable = False
    return {"destination": str(d), "writable": writable, "free_bytes": free_bytes}


def pre_update_checks(conn: Connection, settings: Settings) -> dict[str, Any]:
    """Run the read-only prerequisites for a safe server update (section 5 steps 3–6).
    Returns a list of named checks; the overall gate is 'ready' only if all critical checks pass."""
    checks: list[dict[str, Any]] = []

    # DB connectivity + schema.
    schema = current_schema(conn)
    checks.append({"name": "database_connected", "ok": True, "critical": True,
                   "detail": f"schema {schema['current_head']}"})
    checks.append({"name": "schema_known", "ok": schema["current_level"] is not None, "critical": True,
                   "detail": f"level {schema['current_level']}"})

    # Backup readiness + disk space.
    b = backup_readiness(settings)
    checks.append({"name": "backup_destination_writable", "ok": b["writable"], "critical": True,
                   "detail": b["destination"]})
    enough = b["free_bytes"] is not None and b["free_bytes"] > 500_000_000  # >500 MB free
    checks.append({"name": "sufficient_disk_space", "ok": bool(enough), "critical": True,
                   "detail": (f"{b['free_bytes']} bytes free" if b["free_bytes"] is not None else "unknown")})

    # Not already mid-maintenance.
    state = get_system_state(conn)
    checks.append({"name": "not_in_maintenance", "ok": not state["maintenance_mode"], "critical": False,
                   "detail": "maintenance active" if state["maintenance_mode"] else "idle"})

    ready = all(c["ok"] for c in checks if c["critical"])
    return {"ready": ready, "checks": checks, "backup": b, "database": schema}


# --- Update audit trail ------------------------------------------------------------------------

def record_event(conn: Connection, *, component: str, event: str, from_version: str | None = None,
                 to_version: str | None = None, channel: str | None = None, outcome: str | None = None,
                 actor: str | None = None, detail: dict[str, Any] | None = None) -> None:
    conn.execute(
        text("INSERT INTO update_event(component, event, from_version, to_version, channel, outcome, actor, detail) "
             "VALUES (:c, :e, :fv, :tv, :ch, :o, :a, CAST(:d AS jsonb))"),
        {"c": component, "e": event, "fv": from_version, "tv": to_version, "ch": channel,
         "o": outcome, "a": actor, "d": json.dumps(detail) if detail is not None else None},
    )


def list_events(conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("SELECT component, event, from_version, to_version, channel, outcome, actor, detail, at "
             "FROM update_event ORDER BY at DESC LIMIT :lim"),
        {"lim": limit},
    ).mappings().all()
    return [dict(r) for r in rows]
