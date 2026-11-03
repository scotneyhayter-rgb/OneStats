"""Research job store + lifecycle (Internet Research Engine).

Persistence and state machine for ``research_job`` / ``research_finding`` / ``research_fetch``. Modelled
on the Phase 9 AutoSync engine (lease + heartbeat + checkpoint + retry + startup reconciliation) but
decoupled from connectors and with an explicit user-controlled ``paused`` state.

State machine:
    pending ──claim──▶ running ──complete──▶ succeeded
       ▲                 │  │  └──fail(retries left)──▶ pending (backoff)
       │                 │  └──────fail(exhausted)─────▶ failed
    resume              pause / cancel
       │                 ▼
     paused ◀────────────┘      cancel ▶ cancelled
    interrupted (lease expired on crash) ──reconcile──▶ pending | failed

Every mutation is audited and workspace-scoped (the caller runs inside a ``workspace_transaction`` so
FORCE RLS binds every statement to the one workspace).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

DEPTHS = ("quick", "standard", "deep")
ACTIVE = ("pending", "running", "paused", "interrupted")
DEFAULT_LEASE_SECONDS = 120
DEFAULT_MAX_ATTEMPTS = 3

# Per-depth budgets: how many candidate pages a run will examine in total, and per worker step.
DEPTH_BUDGET = {"quick": 8, "standard": 25, "deep": 60}
STEP_BATCH = 5  # pages processed per worker tick before re-checking pause/cancel and heartbeating


def compute_dedup_key(query: str, context: dict[str, Any] | None) -> str:
    """Stable key for duplicate-job suppression: normalised query + sorted context."""
    norm_q = " ".join((query or "").lower().split())
    ctx = json.dumps(context or {}, sort_keys=True, default=str)
    return hashlib.sha256(f"{norm_q}|{ctx}".encode()).hexdigest()


def _row(conn: Connection, job_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text("SELECT * FROM research_job WHERE id = :id"), {"id": job_id}).mappings().first()
    return dict(r) if r else None


get_job = _row


def create_job(conn: Connection, workspace_id: UUID, actor: str, *, query: str,
               depth: str = "standard", context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Queue an investigation. Raises ``duplicate_active_job`` if an active job already covers the same
    normalised query+context in this workspace (idempotency)."""
    if not (query or "").strip():
        raise ValueError("query_required")
    if depth not in DEPTHS:
        raise ValueError("invalid_depth")
    dedup = compute_dedup_key(query, context)
    existing = conn.execute(
        text("SELECT id FROM research_job WHERE workspace_id = :w AND dedup_key = :d "
             "AND status IN ('pending','running','paused','interrupted')"),
        {"w": workspace_id, "d": dedup},
    ).scalar_one_or_none()
    if existing is not None:
        raise ValueError("duplicate_active_job")
    jid = conn.execute(
        text("INSERT INTO research_job(workspace_id, query, depth, context, dedup_key, progress, created_by) "
             "VALUES (:w, :q, :dp, CAST(:ctx AS jsonb), :d, CAST(:pr AS jsonb), :by) RETURNING id"),
        {"w": workspace_id, "q": query.strip(), "dp": depth,
         "ctx": json.dumps(context) if context is not None else None, "d": dedup,
         "pr": json.dumps({"phase": "queued", "sources_examined": 0, "findings": 0}), "by": actor},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "research.job_created", entity="research_job",
                      entity_id=str(jid), after={"query": query.strip(), "depth": depth})
    return _row(conn, jid)


def list_jobs(conn: Connection, workspace_id: UUID, *, status: str | None = None,
              limit: int = 50) -> list[dict[str, Any]]:
    sql = "SELECT * FROM research_job WHERE workspace_id = :w"
    params: dict[str, Any] = {"w": workspace_id, "lim": limit}
    if status:
        sql += " AND status = :st"
        params["st"] = status
    sql += " ORDER BY created_at DESC LIMIT :lim"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def claim_job(conn: Connection, workspace_id: UUID, actor: str, job_id: UUID, *,
              lease_seconds: int = DEFAULT_LEASE_SECONDS) -> dict[str, Any] | None:
    """Claim one specific pending/interrupted job (mark running under a fresh lease)."""
    res = conn.execute(
        text("UPDATE research_job SET status = 'running', lease_owner = :o, "
             "lease_expires_at = now() + make_interval(secs => :ls), "
             "started_at = COALESCE(started_at, now()), updated_at = now() "
             "WHERE id = :id AND workspace_id = :w AND status IN ('pending','interrupted')"),
        {"o": actor, "ls": lease_seconds, "id": job_id, "w": workspace_id},
    )
    return _row(conn, job_id) if res.rowcount else None


def claim_next_job(conn: Connection, workspace_id: UUID, actor: str, *,
                   lease_seconds: int = DEFAULT_LEASE_SECONDS) -> dict[str, Any] | None:
    """Atomically claim the next unleased pending/interrupted job (oldest first)."""
    row = conn.execute(
        text("SELECT id FROM research_job WHERE workspace_id = :w AND status IN ('pending','interrupted') "
             "AND (lease_expires_at IS NULL OR lease_expires_at < now()) "
             "ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1"),
        {"w": workspace_id},
    ).scalar_one_or_none()
    if row is None:
        return None
    return claim_job(conn, workspace_id, actor, row, lease_seconds=lease_seconds)


def heartbeat(conn: Connection, job_id: UUID, *, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> None:
    conn.execute(
        text("UPDATE research_job SET lease_expires_at = now() + make_interval(secs => :ls), "
             "updated_at = now() WHERE id = :id AND status = 'running'"),
        {"ls": lease_seconds, "id": job_id},
    )


def save_checkpoint(conn: Connection, job_id: UUID, checkpoint: dict[str, Any], *,
                    progress: dict[str, Any] | None = None) -> None:
    conn.execute(
        text("UPDATE research_job SET checkpoint = CAST(:c AS jsonb), "
             "progress = COALESCE(CAST(:p AS jsonb), progress), updated_at = now() WHERE id = :id"),
        {"c": json.dumps(checkpoint, default=str),
         "p": json.dumps(progress, default=str) if progress is not None else None, "id": job_id},
    )


def current_status(conn: Connection, job_id: UUID) -> str | None:
    return conn.execute(text("SELECT status FROM research_job WHERE id = :id"), {"id": job_id}).scalar_one_or_none()


def complete_job(conn: Connection, workspace_id: UUID, actor: str, job_id: UUID, *,
                 progress: dict[str, Any] | None = None) -> dict[str, Any]:
    conn.execute(
        text("UPDATE research_job SET status = 'succeeded', finished_at = now(), lease_owner = NULL, "
             "lease_expires_at = NULL, progress = COALESCE(CAST(:p AS jsonb), progress), updated_at = now() "
             "WHERE id = :id"),
        {"p": json.dumps(progress, default=str) if progress is not None else None, "id": job_id},
    )
    audit.write_audit(conn, workspace_id, actor, "research.job_succeeded", entity="research_job", entity_id=str(job_id))
    return _row(conn, job_id)


def fail_job(conn: Connection, workspace_id: UUID, actor: str, job_id: UUID, *, error: str,
             retry: bool = True, backoff_seconds: int = 30) -> dict[str, Any]:
    job = _row(conn, job_id)
    if job is None:
        raise ValueError("job_not_found")
    attempts = (job["attempts"] or 0) + 1
    can_retry = retry and attempts < (job["max_attempts"] or DEFAULT_MAX_ATTEMPTS)
    if can_retry:
        conn.execute(
            text("UPDATE research_job SET status = 'pending', attempts = :a, last_error = :e, "
                 "lease_owner = NULL, lease_expires_at = NULL, updated_at = now() WHERE id = :id"),
            {"a": attempts, "e": error[:500], "id": job_id},
        )
    else:
        conn.execute(
            text("UPDATE research_job SET status = 'failed', attempts = :a, last_error = :e, finished_at = now(), "
                 "lease_owner = NULL, lease_expires_at = NULL, updated_at = now() WHERE id = :id"),
            {"a": attempts, "e": error[:500], "id": job_id},
        )
    audit.write_audit(conn, workspace_id, actor, "research.job_failed", entity="research_job",
                      entity_id=str(job_id), after={"attempts": attempts, "retry": can_retry})
    return _row(conn, job_id)


def pause_job(conn: Connection, workspace_id: UUID, actor: str, job_id: UUID) -> dict[str, Any]:
    """Request a pause. A running job is marked paused and its lease released; the worker observes the
    status between pages and stops, having checkpointed its frontier."""
    conn.execute(
        text("UPDATE research_job SET status = 'paused', lease_owner = NULL, lease_expires_at = NULL, "
             "updated_at = now() WHERE id = :id AND workspace_id = :w "
             "AND status IN ('pending','running','interrupted')"),
        {"id": job_id, "w": workspace_id},
    )
    audit.write_audit(conn, workspace_id, actor, "research.job_paused", entity="research_job", entity_id=str(job_id))
    return _row(conn, job_id)


def resume_job(conn: Connection, workspace_id: UUID, actor: str, job_id: UUID) -> dict[str, Any]:
    conn.execute(
        text("UPDATE research_job SET status = 'pending', last_error = NULL, updated_at = now() "
             "WHERE id = :id AND workspace_id = :w AND status = 'paused'"),
        {"id": job_id, "w": workspace_id},
    )
    audit.write_audit(conn, workspace_id, actor, "research.job_resumed", entity="research_job", entity_id=str(job_id))
    return _row(conn, job_id)


def cancel_job(conn: Connection, workspace_id: UUID, actor: str, job_id: UUID) -> dict[str, Any]:
    conn.execute(
        text("UPDATE research_job SET status = 'cancelled', finished_at = now(), lease_owner = NULL, "
             "lease_expires_at = NULL, updated_at = now() WHERE id = :id AND workspace_id = :w "
             "AND status IN ('pending','running','paused','interrupted')"),
        {"id": job_id, "w": workspace_id},
    )
    audit.write_audit(conn, workspace_id, actor, "research.job_cancelled", entity="research_job", entity_id=str(job_id))
    return _row(conn, job_id)


def reconcile_stale_jobs(conn: Connection, workspace_id: UUID, actor: str) -> dict[str, int]:
    """Recover jobs left 'running' with an expired lease (e.g. after a PC shutdown): requeue those with
    retries left (status 'interrupted' → re-claimable), fail the rest. Nothing is falsely running."""
    stale = conn.execute(
        text("SELECT id, attempts, max_attempts FROM research_job WHERE workspace_id = :w "
             "AND status = 'running' AND (lease_expires_at IS NULL OR lease_expires_at < now())"),
        {"w": workspace_id},
    ).mappings().all()
    requeued = failed = 0
    for j in stale:
        attempts = (j["attempts"] or 0) + 1
        if attempts < (j["max_attempts"] or DEFAULT_MAX_ATTEMPTS):
            conn.execute(
                text("UPDATE research_job SET status = 'interrupted', attempts = :a, lease_owner = NULL, "
                     "lease_expires_at = NULL, last_error = 'interrupted (lease expired)', updated_at = now() "
                     "WHERE id = :id"),
                {"a": attempts, "id": j["id"]},
            )
            requeued += 1
        else:
            conn.execute(
                text("UPDATE research_job SET status = 'failed', attempts = :a, finished_at = now(), "
                     "lease_owner = NULL, lease_expires_at = NULL, "
                     "last_error = 'interrupted; retries exhausted', updated_at = now() WHERE id = :id"),
                {"a": attempts, "id": j["id"]},
            )
            failed += 1
    if requeued or failed:
        audit.write_audit(conn, workspace_id, actor, "research.jobs_reconciled", entity="workspace",
                          entity_id=str(workspace_id), after={"requeued": requeued, "failed": failed})
    return {"requeued": requeued, "failed": failed}


# ---- findings + fetch provenance ------------------------------------------------------------------

def record_fetch(conn: Connection, workspace_id: UUID, job_id: UUID, *, url: str, outcome: str,
                 http_status: int | None = None, content_type: str | None = None, nbytes: int | None = None,
                 content_sha256: str | None = None, detail: str | None = None) -> None:
    """Record what was actually retrieved (searched vs blocked vs failed), idempotent per (job, url)."""
    conn.execute(
        text("INSERT INTO research_fetch(workspace_id, job_id, url, outcome, http_status, content_type, "
             "bytes, content_sha256, detail) VALUES (:w, :j, :u, :o, :hs, :ct, :b, :sha, :d) "
             "ON CONFLICT ON CONSTRAINT uq_research_fetch DO UPDATE SET outcome = :o, http_status = :hs, "
             "content_type = :ct, bytes = :b, content_sha256 = :sha, detail = :d, retrieved_at = now()"),
        {"w": workspace_id, "j": job_id, "u": url[:2000], "o": outcome, "hs": http_status, "ct": content_type,
         "b": nbytes, "sha": (content_sha256 or None), "d": (detail or None) and detail[:500]},
    )


def record_finding(conn: Connection, workspace_id: UUID, job_id: UUID, *, url: str, kind: str,
                   classification: str = "unknown", confidence: float | None = None,
                   title: str | None = None, summary: str | None = None, source_host: str | None = None,
                   extracted: dict[str, Any] | None = None, raw_excerpt: str | None = None,
                   content_sha256: str | None = None) -> UUID | None:
    """Persist a reviewable finding, idempotent per (job, url). Returns the finding id, or None if a
    reviewer has already acted on this url for this job (we never clobber a human decision)."""
    locked = conn.execute(
        text("SELECT id, status FROM research_finding WHERE workspace_id = :w AND job_id = :j AND url = :u"),
        {"w": workspace_id, "j": job_id, "u": url[:2000]},
    ).mappings().first()
    if locked and locked["status"] != "pending_review":
        return None  # a reviewer accepted/rejected/linked it — leave it untouched
    fid = conn.execute(
        text("INSERT INTO research_finding(workspace_id, job_id, url, source_host, title, kind, "
             "classification, confidence, summary, extracted, raw_excerpt, content_sha256, retrieved_at) "
             "VALUES (:w, :j, :u, :host, :t, :k, :cl, :cf, :sm, CAST(:ex AS jsonb), :rx, :sha, now()) "
             "ON CONFLICT ON CONSTRAINT uq_research_finding DO UPDATE SET title = :t, kind = :k, "
             "classification = :cl, confidence = :cf, summary = :sm, extracted = CAST(:ex AS jsonb), "
             "raw_excerpt = :rx, content_sha256 = :sha, source_host = :host, updated_at = now() RETURNING id"),
        {"w": workspace_id, "j": job_id, "u": url[:2000], "host": source_host, "t": title, "k": kind,
         "cl": classification, "cf": confidence, "sm": summary,
         "ex": json.dumps(extracted, default=str) if extracted is not None else None,
         "rx": raw_excerpt, "sha": content_sha256},
    ).scalar_one()
    return fid


def list_findings(conn: Connection, workspace_id: UUID, *, job_id: UUID | None = None,
                  status: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    sql = "SELECT * FROM research_finding WHERE workspace_id = :w"
    params: dict[str, Any] = {"w": workspace_id, "lim": limit}
    if job_id is not None:
        sql += " AND job_id = :j"
        params["j"] = job_id
    if status:
        sql += " AND status = :st"
        params["st"] = status
    sql += " ORDER BY (confidence IS NULL), confidence DESC, created_at DESC LIMIT :lim"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def get_finding(conn: Connection, workspace_id: UUID, finding_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(
        text("SELECT * FROM research_finding WHERE id = :id AND workspace_id = :w"),
        {"id": finding_id, "w": workspace_id},
    ).mappings().first()
    return dict(r) if r else None


def set_finding_status(conn: Connection, workspace_id: UUID, actor: str, finding_id: UUID, *,
                       status: str, notes: str | None = None) -> dict[str, Any]:
    """Record a reviewer's decision on a finding. This DOES NOT import or approve anything — it only
    tracks the triage state; acceptance into official statistics still goes through the existing
    reconstruction + Phase 7 approval workflow."""
    if status not in ("pending_review", "accepted", "rejected", "linked", "superseded"):
        raise ValueError("invalid_status")
    res = conn.execute(
        text("UPDATE research_finding SET status = :st, notes = COALESCE(:nt, notes), reviewed_by = :by, "
             "reviewed_at = now(), updated_at = now() WHERE id = :id AND workspace_id = :w"),
        {"st": status, "nt": notes, "by": actor, "id": finding_id, "w": workspace_id},
    )
    if not res.rowcount:
        raise ValueError("finding_not_found")
    audit.write_audit(conn, workspace_id, actor, "research.finding_reviewed", entity="research_finding",
                      entity_id=str(finding_id), after={"status": status})
    return get_finding(conn, workspace_id, finding_id)


def job_findings_count(conn: Connection, workspace_id: UUID, job_id: UUID) -> dict[str, int]:
    rows = conn.execute(
        text("SELECT status, count(*) AS n FROM research_finding WHERE workspace_id = :w AND job_id = :j "
             "GROUP BY status"),
        {"w": workspace_id, "j": job_id},
    ).mappings().all()
    return {r["status"]: r["n"] for r in rows}
