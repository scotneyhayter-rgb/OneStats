"""Resumable Cricsheet historical backfill (Part G).

A backfill walks a format's entire Cricsheet bundle in controlled batches, importing each match through
the orchestrator. It is:

  * Resumable: progress lives in the DB (``cricsheet_backfill``) and in ``cricsheet_import_log``. A run
    skips matches already logged, so it picks up where it left off after a pause or an app restart.
  * Controllable: pause / resume / cancel via status; a paused or cancelled backfill does no work.
  * Accurate over fast: it reuses the idempotent importer (no duplicates, verified scorecards preserved)
    and records genuine counts. It never claims Cricsheet is complete — matches Cricsheet lacks simply
    never appear here and stay discoverable through other sources.

The batch runner takes the already-downloaded bundle bytes, so downloading (network) stays in the
worker/caller and this logic is deterministic and testable offline.
"""
from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit
from onestats.domain.intl import cricsheet_download as dl

_ACTIVE = ("pending", "running", "paused")


def _row(conn: Connection, workspace_id: UUID, fmt: str) -> dict[str, Any] | None:
    r = conn.execute(
        text("SELECT * FROM cricsheet_backfill WHERE workspace_id = :w AND format = :f"),
        {"w": workspace_id, "f": fmt},
    ).mappings().first()
    return dict(r) if r else None


def start(conn: Connection, workspace_id: UUID, actor: str, fmt: str) -> dict[str, Any]:
    """Create or (re)start a backfill for a format. Resets a finished/cancelled one to pending; leaves
    an in-flight one as it is. Already-imported matches are still skipped on the next batch, so a restart
    never re-does completed work."""
    if fmt not in dl.BUNDLES:
        raise ValueError("invalid_format")
    existing = _row(conn, workspace_id, fmt)
    if existing is None:
        conn.execute(
            text("INSERT INTO cricsheet_backfill(workspace_id, format, status, started_at) "
                 "VALUES (:w, :f, 'pending', now())"),
            {"w": workspace_id, "f": fmt},
        )
    else:
        conn.execute(
            text("UPDATE cricsheet_backfill SET status = 'pending', last_error = NULL, "
                 "started_at = COALESCE(started_at, now()), finished_at = NULL, updated_at = now() "
                 "WHERE id = :id"),
            {"id": existing["id"]},
        )
    audit.write_audit(conn, workspace_id, actor, "cricsheet.backfill.start", entity="cricsheet_backfill",
                      entity_id=fmt, after={"format": fmt})
    return _row(conn, workspace_id, fmt)  # type: ignore[return-value]


def set_status(conn: Connection, workspace_id: UUID, actor: str, fmt: str, status: str) -> dict[str, Any]:
    """pause / resume (-> pending) / cancel a backfill."""
    target = {"pause": "paused", "resume": "pending", "cancel": "cancelled"}.get(status)
    if target is None:
        raise ValueError("invalid_control")
    row = _row(conn, workspace_id, fmt)
    if row is None:
        raise ValueError("backfill_not_found")
    conn.execute(
        text("UPDATE cricsheet_backfill SET status = :s, "
             "finished_at = CASE WHEN :s = 'cancelled' THEN now() ELSE finished_at END, "
             "updated_at = now() WHERE id = :id"),
        {"s": target, "id": row["id"]},
    )
    audit.write_audit(conn, workspace_id, actor, f"cricsheet.backfill.{status}",
                      entity="cricsheet_backfill", entity_id=fmt)
    return _row(conn, workspace_id, fmt)  # type: ignore[return-value]


def run_batch(conn: Connection, workspace_id: UUID, actor: str, fmt: str, bundle_bytes: bytes, *,
              batch_size: int = 50) -> dict[str, Any]:
    """Process up to ``batch_size`` not-yet-done matches from the bundle. No-op when the backfill is
    paused/cancelled/completed/absent. Skips matches already in the import log (resumability), so calling
    this repeatedly (e.g. once per worker tick) walks the whole bundle and then marks it completed."""
    row = _row(conn, workspace_id, fmt)
    if row is None or row["status"] in ("paused", "cancelled", "completed"):
        return {"ran": False, "status": (row or {}).get("status"), "processed": 0}

    # every ref already attempted (imported, skipped OR failed) is not reprocessed, so the backfill
    # progresses to completion; failed ones can be retried explicitly later.
    done = set(conn.execute(
        text("SELECT source_ref FROM cricsheet_import_log WHERE workspace_id = :w"),
        {"w": workspace_id},
    ).scalars().all())

    # iterate the bundle, skip already-done, process a bounded batch
    pending = ((ref, b, doc) for ref, b, doc in dl.iter_bundle(bundle_bytes) if ref not in done)
    all_refs = [ref for ref, _b, _d in dl.iter_bundle(bundle_bytes)]
    bundle_sha = hashlib.sha256(bundle_bytes).hexdigest()

    conn.execute(text("UPDATE cricsheet_backfill SET status='running', total_seen=:t, "
                      "bundle_sha256=:sha, updated_at=now() WHERE id=:id"),
                 {"t": len(all_refs), "sha": bundle_sha, "id": row["id"]})

    result = dl.import_matches(conn, workspace_id, actor, pending, max_items=batch_size)
    processed_now = result["processed"]
    # after this batch, everything previously done plus what we just processed; done when none remain
    remaining = max(len(all_refs) - len(done) - processed_now, 0)
    completed = remaining == 0
    conn.execute(
        text("UPDATE cricsheet_backfill SET status = :st, "
             "processed = processed + :p, imported = imported + :imp, skipped = skipped + :sk, "
             "failed = failed + :fl, last_ref = COALESCE(:lr, last_ref), "
             "finished_at = CASE WHEN :st = 'completed' THEN now() ELSE finished_at END, "
             "updated_at = now() WHERE id = :id"),
        {"st": "completed" if completed else "running", "p": processed_now,
         "imp": result["awaiting_verification"], "sk": result["skipped"], "fl": result["failed"],
         "lr": result["last_ref"], "id": row["id"]},
    )
    return {"ran": True, "status": "completed" if completed else "running",
            "processed": processed_now, "remaining": max(remaining, 0),
            "awaiting_verification": result["awaiting_verification"],
            "skipped": result["skipped"], "failed": result["failed"]}


def get(conn: Connection, workspace_id: UUID, fmt: str) -> dict[str, Any] | None:
    return _row(conn, workspace_id, fmt)


def list_all(conn: Connection, workspace_id: UUID) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        text("SELECT * FROM cricsheet_backfill WHERE workspace_id = :w ORDER BY format"),
        {"w": workspace_id}).mappings().all()]
