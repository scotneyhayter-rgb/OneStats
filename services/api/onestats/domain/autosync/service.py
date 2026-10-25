"""AutoSync orchestration (Phase 9, Stages 9.4/9.10/9.11).

Ties the background job engine to the connectors and the discovery services: job handlers for new /
updated / historical discovery, a Sync Now that enqueues and runs a real job, a resumable
Discover-Entire-Workspace-History pass, startup reconciliation, and a dashboard summary built from
real database counts (never fabricated).
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain.autosync import discovery, jobs
from onestats.domain.autosync.connectors import STATUS_INTERFACE_ONLY, catalog

SYSTEM_ACTOR = "00000000-0000-0000-0000-000000000000"


def _source_for_job(conn: Connection, workspace_id: UUID, job: dict[str, Any]) -> dict[str, Any] | None:
    """The enabled sync_source this job targets (matched by connector_id or name)."""
    return conn.execute(
        text("SELECT * FROM sync_source WHERE workspace_id = :w AND enabled = true "
             "AND (connector_id = :s OR name = :s) LIMIT 1"),
        {"w": workspace_id, "s": job["source_system"]},
    ).mappings().first()


def _connector_for(source_row: dict[str, Any]):
    connector = catalog.get(source_row["connector_id"])
    if getattr(connector.info, "status", None) == STATUS_INTERFACE_ONLY:
        raise NotImplementedError(
            f"{source_row['connector_id']}: connector not implemented (awaiting verified access)")
    return connector


def _handle_new(conn: Connection, workspace_id: UUID, actor: str, job: dict[str, Any]) -> dict[str, Any]:
    src = _source_for_job(conn, workspace_id, job)
    if src is None:
        raise ValueError("no enabled source for job")
    connector = _connector_for(dict(src))
    out = discovery.discover_new(conn, workspace_id, actor, connector=connector, source_id=src["id"],
                                 mode="review_required", scope_key="new")
    return out


def _handle_updated(conn: Connection, workspace_id: UUID, actor: str, job: dict[str, Any]) -> dict[str, Any]:
    src = _source_for_job(conn, workspace_id, job)
    if src is None:
        raise ValueError("no enabled source for job")
    connector = _connector_for(dict(src))
    return discovery.discover_updated(conn, workspace_id, actor, connector=connector, source_id=src["id"])


def _handle_historical(conn: Connection, workspace_id: UUID, actor: str, job: dict[str, Any]) -> dict[str, Any]:
    src = _source_for_job(conn, workspace_id, job)
    if src is None:
        raise ValueError("no enabled source for job")
    connector = _connector_for(dict(src))
    scopes = (job.get("progress") or {}).get("scopes") or []
    done = set((job.get("checkpoint") or {}).get("done") or [])
    return discover_history(conn, workspace_id, actor, connector=connector, source_id=src["id"],
                            scopes=scopes, done=done, job_id=job["id"])


def register_handlers() -> None:
    jobs.register_handler("new", _handle_new)
    jobs.register_handler("updated", _handle_updated)
    jobs.register_handler("historical", _handle_historical)
    jobs.register_handler("manual", _handle_new)


register_handlers()


def discover_history(conn: Connection, workspace_id: UUID, actor: str, *, connector: Any,
                     source_id: UUID | None, scopes: list[dict[str, Any]], done: set | None = None,
                     job_id: UUID | None = None) -> dict[str, Any]:
    """Discover-Entire-Workspace-History: run discovery for each configured scope, recording coverage
    per scope and checkpointing so an interruption resumes rather than restarts. A scope whose source
    has no coverage is recorded 'no_source'/'failed' — never silently 'searched'."""
    done = set(done or [])
    searched = failed = 0
    for scope in scopes:
        key = scope.get("key") or json.dumps(scope, sort_keys=True)
        if key in done:
            continue
        out = discovery.discover_new(conn, workspace_id, actor, connector=connector, source_id=source_id,
                                     mode="review_required", scope_key=key, scope=scope)
        if out.get("status") == "failed":
            failed += 1
        else:
            searched += 1
        done.add(key)
        if job_id is not None:
            jobs.save_checkpoint(conn, job_id, {"done": sorted(done)},
                                 progress={"scopes": scopes, "searched": searched, "failed": failed})
    return {"status": "ok", "scopes": len(scopes), "searched": searched, "failed": failed}


def sync_now(conn: Connection, workspace_id: UUID, actor: str, *, source_system: str, kind: str = "manual") -> dict[str, Any]:
    """Enqueue and immediately run a real job (the dashboard's Sync Now). Duplicate-active prevention
    applies; returns the job and its outcome."""
    job = jobs.create_job(conn, workspace_id, actor, source_system=source_system, kind=kind)
    claimed = jobs.claim_next_job(conn, workspace_id, actor)
    if claimed is None or claimed["id"] != job["id"]:
        return {"job": job, "ran": False}
    done = jobs.run_job(conn, workspace_id, actor, claimed)
    return {"job": done, "ran": True}


def startup_reconcile(conn: Connection, workspace_id: UUID, actor: str = SYSTEM_ACTOR) -> dict[str, int]:
    """Called when the app/service starts: recover jobs left running by a shutdown (offline catch-up)."""
    return jobs.reconcile_stale_jobs(conn, workspace_id, actor)


def dashboard_summary(conn: Connection, workspace_id: UUID) -> dict[str, Any]:
    """Real, DB-backed AutoSync status for the dashboard — no fabricated counts."""
    def _scalar(sql: str) -> int:
        return conn.execute(text(sql), {"w": workspace_id}).scalar_one()

    items_by_class = {r["classification"]: r["n"] for r in conn.execute(
        text("SELECT classification, count(*) AS n FROM discovery_item WHERE workspace_id = :w "
             "AND status = 'pending_review' GROUP BY classification"), {"w": workspace_id}).mappings()}
    coverage_by_status = {r["status"]: r["n"] for r in conn.execute(
        text("SELECT status, count(*) AS n FROM discovery_coverage WHERE workspace_id = :w GROUP BY status"),
        {"w": workspace_id}).mappings()}
    last_success = conn.execute(
        text("SELECT max(last_success_at) FROM sync_source WHERE workspace_id = :w"), {"w": workspace_id}).scalar_one()
    return {
        "sources": _scalar("SELECT count(*) FROM sync_source WHERE workspace_id = :w AND enabled = true"),
        "pending_review": _scalar("SELECT count(*) FROM discovery_item WHERE workspace_id = :w AND status = 'pending_review'"),
        "new_matches": items_by_class.get("new", 0),
        "possible_duplicates": items_by_class.get("possible_duplicate", 0),
        "updated_scorecards": _scalar("SELECT count(*) FROM discovery_item WHERE workspace_id = :w "
                                      "AND kind = 'updated_scorecard' AND status = 'pending_review'"),
        "jobs_running": _scalar("SELECT count(*) FROM sync_job WHERE workspace_id = :w AND status = 'running'"),
        "jobs_failed": _scalar("SELECT count(*) FROM sync_job WHERE workspace_id = :w AND status = 'failed'"),
        "coverage": coverage_by_status,
        "last_success_at": last_success.isoformat() if last_success else None,
    }
