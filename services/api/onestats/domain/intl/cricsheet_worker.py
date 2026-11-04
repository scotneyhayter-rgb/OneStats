"""Background tick that advances Cricsheet backfills by downloading and importing one batch.

This is the piece that performs the network download (which must NOT happen in a request handler or a
scheduler-tick transaction). It is designed to ride the existing in-process worker loop exactly like the
scheduler tick: call :func:`run_due` periodically. Each call, per workspace with an active backfill and
per format, downloads that format's Cricsheet bundle once (SSRF-hardened, allow-list enforced) and runs
a single bounded batch. Failures are isolated per workspace/format and recorded on the backfill row —
one bad download never stops the loop or another workspace.

Wiring (to be added to the shared worker loop, next to the scheduler tick):
    from onestats.domain.intl import cricsheet_worker
    cricsheet_worker.run_due(self._engine)
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine

from onestats.db.workspace import workspace_transaction
from onestats.domain.intl import cricsheet_backfill as backfill
from onestats.domain.intl import cricsheet_download as dl

# Attributed to a clearly-labelled system actor for scheduled/background work.
SYSTEM_ACTOR = "00000000-0000-0000-0000-000000000000"


def _candidate_workspaces(engine: Engine, only_workspace: UUID | None) -> list[UUID]:
    """All workspace ids (optionally one). We enumerate the non-RLS ``workspace`` table — the backfill
    table is FORCE-RLS, so which of these actually has an active backfill is read per workspace, inside
    that workspace's transaction."""
    sql = "SELECT id FROM workspace"
    params: dict[str, Any] = {}
    if only_workspace is not None:
        sql += " WHERE id = :w"
        params["w"] = only_workspace
    with engine.begin() as conn:
        return [r[0] for r in conn.execute(text(sql), params).all()]


def run_due(engine: Engine, *, batch_size: int = 25,
            fetcher_factory: Callable[[], Any] | None = None,
            only_workspace: UUID | None = None,
            now: dt.datetime | None = None) -> dict[str, Any]:
    """Advance every active backfill by one downloaded batch. Returns a per-format summary. Safe to call
    on every worker tick: a paused/cancelled/completed backfill is skipped by :func:`run_batch`.
    ``only_workspace`` scopes a run to a single workspace (targeted import / tests)."""
    make = fetcher_factory or dl.make_fetcher
    ran: list[dict[str, Any]] = []
    for wid in _candidate_workspaces(engine, only_workspace):
        # Read the active formats in a short transaction, then release it — the network download must
        # NOT be held inside an open DB transaction (idle-in-transaction / connection held for the fetch).
        with workspace_transaction(engine, wid) as conn:
            formats = [r["format"] for r in backfill.list_all(conn, wid)
                       if r["status"] in ("pending", "running")]

        for fmt in formats:
            # 1. download OUTSIDE any transaction (may take a while for a large bundle)
            try:
                res = dl.fetch_bundle(fmt, fetcher=make())
            except Exception as exc:  # noqa: BLE001 - isolate per workspace/format
                _mark_error(engine, wid, fmt, str(exc))
                ran.append({"workspace_id": str(wid), "format": fmt, "ran": False, "error": str(exc)})
                continue
            if not res.ok:
                _mark_error(engine, wid, fmt, f"download {res.outcome}: {res.detail}")
                ran.append({"workspace_id": str(wid), "format": fmt, "ran": False, "error": res.outcome})
                continue
            # 2. import the batch in a fresh, short transaction (no network held open)
            try:
                with workspace_transaction(engine, wid) as conn:
                    out = backfill.run_batch(conn, wid, SYSTEM_ACTOR, fmt, res.content or b"",
                                             batch_size=batch_size)
                ran.append({"workspace_id": str(wid), "format": fmt, **out})
            except Exception as exc:  # noqa: BLE001
                _mark_error(engine, wid, fmt, str(exc))
                ran.append({"workspace_id": str(wid), "format": fmt, "ran": False, "error": str(exc)})
    return {"ticked": len(ran), "runs": ran}


def _mark_error(engine: Engine, workspace_id: UUID, fmt: str, message: str) -> None:
    """Record a download/import error on the backfill row in its own short transaction."""
    try:
        with workspace_transaction(engine, workspace_id) as conn:
            conn.execute(text("UPDATE cricsheet_backfill SET last_error = :e, updated_at = now() "
                              "WHERE workspace_id = :w AND format = :f"),
                         {"e": message[:2000], "w": workspace_id, "f": fmt})
    except Exception:  # noqa: BLE001, S110 - never let error-logging mask the original failure
        pass
