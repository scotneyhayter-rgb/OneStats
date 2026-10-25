"""AutoSync background job engine (Phase 9, Stage 9.1).

Persistent, workspace-scoped jobs with progress, a resumable checkpoint, lease-based heartbeats and
safe recovery. Designed for the Windows desktop (an in-process runner, no external broker) and
reusable by a future cloud runner.

Restart safety: a running job holds a lease (``lease_owner`` + ``lease_expires_at``) renewed by
``heartbeat``. If the PC powers off, the lease simply expires — the job is never falsely reported
running. On startup, :func:`reconcile_stale_jobs` requeues (or fails) jobs whose lease has expired, so
missed checks resume. Claiming uses ``FOR UPDATE SKIP LOCKED`` for safe controlled concurrency, and a
partial unique index prevents duplicate active jobs per (workspace, source, kind).

Handlers for each job ``kind`` register via :func:`register_handler`; the discovery handlers arrive in
later stages. This module is the engine only.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

STATUSES = ("pending", "running", "succeeded", "failed", "cancelled", "interrupted")
KINDS = ("new", "updated", "historical", "manual")
ACTIVE = ("pending", "running")
DEFAULT_LEASE_SECONDS = 300
DEFAULT_MAX_ATTEMPTS = 3

# handler registry: kind -> callable(conn, workspace_id, actor, job) -> dict (progress) | None
_HANDLERS: dict[str, Callable[..., Any]] = {}


def register_handler(kind: str, fn: Callable[..., Any]) -> None:
    if kind not in KINDS:
        raise ValueError("invalid_job_kind")
    _HANDLERS[kind] = fn


def _row(conn: Connection, job_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text("SELECT * FROM sync_job WHERE id = :id"), {"id": job_id}).mappings().first()
    return dict(r) if r else None


get_job = _row


def create_job(
    conn: Connection, workspace_id: UUID, actor: str, *, source_system: str, kind: str,
    schedule: str | None = None, next_run_at: Any = None, max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Queue a job. Raises ``duplicate_active_job`` if one is already pending/running for this
    (source, kind) — the runner never processes the same work twice concurrently."""
    if kind not in KINDS:
        raise ValueError("invalid_job_kind")
    existing = conn.execute(
        text("SELECT id FROM sync_job WHERE workspace_id = :w AND source_system = :ss AND kind = :k "
             "AND status IN ('pending','running')"),
        {"w": workspace_id, "ss": source_system, "k": kind},
    ).scalar_one_or_none()
    if existing is not None:
        raise ValueError("duplicate_active_job")
    jid = conn.execute(
        text("INSERT INTO sync_job(workspace_id, source_system, kind, schedule, next_run_at, "
             "max_attempts, progress, created_by) "
             "VALUES (:w, :ss, :k, :sch, :nra, :ma, CAST(:p AS jsonb), :by) RETURNING id"),
        {"w": workspace_id, "ss": source_system, "k": kind, "sch": schedule, "nra": next_run_at,
         "ma": max_attempts, "p": json.dumps(progress, default=str) if progress is not None else None, "by": actor},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "autosync.job_created", entity="sync_job",
                      entity_id=str(jid), after={"source_system": source_system, "kind": kind})
    return _row(conn, jid)


def claim_next_job(
    conn: Connection, workspace_id: UUID, actor: str, *, lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> dict[str, Any] | None:
    """Atomically claim the next due, unleased job (pending, or running with an expired lease) and
    mark it running under a fresh lease. Returns the job, or None when nothing is due."""
    row = conn.execute(
        text("SELECT id FROM sync_job WHERE workspace_id = :w "
             "AND status IN ('pending','interrupted') "
             "AND (next_run_at IS NULL OR next_run_at <= now()) "
             "AND (lease_expires_at IS NULL OR lease_expires_at < now()) "
             "ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1"),
        {"w": workspace_id},
    ).scalar_one_or_none()
    if row is None:
        return None
    conn.execute(
        text("UPDATE sync_job SET status = 'running', lease_owner = :o, "
             "lease_expires_at = now() + make_interval(secs => :ls), "
             "started_at = COALESCE(started_at, now()), updated_at = now() WHERE id = :id"),
        {"o": actor, "ls": lease_seconds, "id": row},
    )
    return _row(conn, row)


def claim_job(conn: Connection, workspace_id: UUID, actor: str, job_id: UUID, *,
              lease_seconds: int = DEFAULT_LEASE_SECONDS) -> dict[str, Any] | None:
    """Claim one SPECIFIC pending/interrupted job (mark it running under a fresh lease). Used by
    Sync Now to run exactly the job it created, rather than the oldest due one."""
    res = conn.execute(
        text("UPDATE sync_job SET status = 'running', lease_owner = :o, "
             "lease_expires_at = now() + make_interval(secs => :ls), "
             "started_at = COALESCE(started_at, now()), updated_at = now() "
             "WHERE id = :id AND status IN ('pending','interrupted')"),
        {"o": actor, "ls": lease_seconds, "id": job_id},
    )
    return _row(conn, job_id) if res.rowcount else None


def heartbeat(conn: Connection, job_id: UUID, *, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> None:
    """Renew a running job's lease (called periodically by the worker)."""
    conn.execute(
        text("UPDATE sync_job SET lease_expires_at = now() + make_interval(secs => :ls), updated_at = now() "
             "WHERE id = :id AND status = 'running'"),
        {"ls": lease_seconds, "id": job_id},
    )


def save_checkpoint(conn: Connection, job_id: UUID, checkpoint: dict[str, Any], *,
                    progress: dict[str, Any] | None = None) -> None:
    """Persist a resume point (and optionally progress) so an interruption resumes, not restarts."""
    conn.execute(
        text("UPDATE sync_job SET checkpoint = CAST(:c AS jsonb), "
             "progress = COALESCE(CAST(:p AS jsonb), progress), updated_at = now() WHERE id = :id"),
        {"c": json.dumps(checkpoint, default=str), "p": json.dumps(progress, default=str) if progress is not None else None, "id": job_id},
    )


def complete_job(conn: Connection, workspace_id: UUID, actor: str, job_id: UUID, *,
                 progress: dict[str, Any] | None = None) -> dict[str, Any]:
    conn.execute(
        text("UPDATE sync_job SET status = 'succeeded', finished_at = now(), lease_owner = NULL, "
             "lease_expires_at = NULL, progress = COALESCE(CAST(:p AS jsonb), progress), updated_at = now() "
             "WHERE id = :id"),
        {"p": json.dumps(progress, default=str) if progress is not None else None, "id": job_id},
    )
    audit.write_audit(conn, workspace_id, actor, "autosync.job_succeeded", entity="sync_job", entity_id=str(job_id))
    return _row(conn, job_id)


def fail_job(conn: Connection, workspace_id: UUID, actor: str, job_id: UUID, *, error: str,
             retry: bool = True, backoff_seconds: int = 60) -> dict[str, Any]:
    """Record a failure. If retries remain, requeue with backoff; otherwise mark failed. Never leaves
    a job half-running."""
    job = _row(conn, job_id)
    if job is None:
        raise ValueError("job_not_found")
    attempts = (job["attempts"] or 0) + 1
    can_retry = retry and attempts < (job["max_attempts"] or DEFAULT_MAX_ATTEMPTS)
    if can_retry:
        conn.execute(
            text("UPDATE sync_job SET status = 'pending', attempts = :a, last_error = :e, "
                 "lease_owner = NULL, lease_expires_at = NULL, "
                 "next_run_at = now() + make_interval(secs => :bo), updated_at = now() WHERE id = :id"),
            {"a": attempts, "e": error, "bo": backoff_seconds, "id": job_id},
        )
    else:
        conn.execute(
            text("UPDATE sync_job SET status = 'failed', attempts = :a, last_error = :e, finished_at = now(), "
                 "lease_owner = NULL, lease_expires_at = NULL, updated_at = now() WHERE id = :id"),
            {"a": attempts, "e": error, "id": job_id},
        )
    audit.write_audit(conn, workspace_id, actor, "autosync.job_failed", entity="sync_job",
                      entity_id=str(job_id), after={"attempts": attempts, "retry": can_retry})
    return _row(conn, job_id)


def cancel_job(conn: Connection, workspace_id: UUID, actor: str, job_id: UUID) -> dict[str, Any]:
    conn.execute(
        text("UPDATE sync_job SET status = 'cancelled', finished_at = now(), lease_owner = NULL, "
             "lease_expires_at = NULL, updated_at = now() "
             "WHERE id = :id AND status IN ('pending','running','interrupted')"),
        {"id": job_id},
    )
    audit.write_audit(conn, workspace_id, actor, "autosync.job_cancelled", entity="sync_job", entity_id=str(job_id))
    return _row(conn, job_id)


def reconcile_stale_jobs(conn: Connection, workspace_id: UUID, actor: str) -> dict[str, int]:
    """Recover jobs left 'running' with an expired lease (e.g. after a PC shutdown): requeue those
    with retries left, fail the rest. Call on application/service startup. Nothing is falsely running.
    Returns how many were requeued vs failed."""
    stale = conn.execute(
        text("SELECT id, attempts, max_attempts FROM sync_job WHERE workspace_id = :w "
             "AND status = 'running' AND (lease_expires_at IS NULL OR lease_expires_at < now())"),
        {"w": workspace_id},
    ).mappings().all()
    requeued = failed = 0
    for j in stale:
        attempts = (j["attempts"] or 0) + 1
        if attempts < (j["max_attempts"] or DEFAULT_MAX_ATTEMPTS):
            conn.execute(
                text("UPDATE sync_job SET status = 'interrupted', attempts = :a, lease_owner = NULL, "
                     "lease_expires_at = NULL, last_error = 'interrupted (lease expired)', updated_at = now() "
                     "WHERE id = :id"),
                {"a": attempts, "id": j["id"]},
            )
            requeued += 1
        else:
            conn.execute(
                text("UPDATE sync_job SET status = 'failed', attempts = :a, finished_at = now(), "
                     "lease_owner = NULL, lease_expires_at = NULL, "
                     "last_error = 'interrupted; retries exhausted', updated_at = now() WHERE id = :id"),
                {"a": attempts, "id": j["id"]},
            )
            failed += 1
    if requeued or failed:
        audit.write_audit(conn, workspace_id, actor, "autosync.jobs_reconciled", entity="workspace",
                          entity_id=str(workspace_id), after={"requeued": requeued, "failed": failed})
    return {"requeued": requeued, "failed": failed}


def list_jobs(conn: Connection, workspace_id: UUID, *, status: str | None = None,
              limit: int = 100) -> list[dict[str, Any]]:
    sql = "SELECT * FROM sync_job WHERE workspace_id = :w"
    params: dict[str, Any] = {"w": workspace_id, "lim": limit}
    if status:
        sql += " AND status = :st"
        params["st"] = status
    sql += " ORDER BY created_at DESC LIMIT :lim"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def run_job(conn: Connection, workspace_id: UUID, actor: str, job: dict[str, Any]) -> dict[str, Any]:
    """Execute one claimed job through its registered handler, with failure handling. The handler
    does the discovery work and may checkpoint; here it is wrapped so a crash fails/retries cleanly."""
    handler = _HANDLERS.get(job["kind"])
    if handler is None:
        return fail_job(conn, workspace_id, actor, job["id"], error=f"no handler for kind '{job['kind']}'", retry=False)
    try:
        progress = handler(conn, workspace_id, actor, job)
    except Exception as exc:  # noqa: BLE001 - any handler error becomes a recorded job failure/retry
        return fail_job(conn, workspace_id, actor, job["id"], error=str(exc))
    return complete_job(conn, workspace_id, actor, job["id"], progress=progress if isinstance(progress, dict) else None)


def run_due_jobs(conn: Connection, workspace_id: UUID, actor: str, *, max_jobs: int = 10) -> dict[str, int]:
    """Claim and run up to ``max_jobs`` due jobs for a workspace (the in-process runner's tick)."""
    ran = 0
    while ran < max_jobs:
        job = claim_next_job(conn, workspace_id, actor)
        if job is None:
            break
        run_job(conn, workspace_id, actor, job)
        ran += 1
    return {"ran": ran}
