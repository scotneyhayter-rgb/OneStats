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
from typing import Any, Callable
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine

from onestats.db.workspace import workspace_transaction
from onestats.domain.intl import cricsheet_backfill as backfill
from onestats.domain.intl import cricsheet_download as dl

# Attributed to a clearly-labelled system actor for scheduled/background work.
SYSTEM_ACTOR = "00000000-0000-0000-0000-000000000000"


def _active_workspaces(engine: Engine) -> list[UUID]:
    with engine.connect() as conn:
        return list(conn.execute(text(
            "SELECT DISTINCT workspace_id FROM cricsheet_backfill WHERE status in ('pending','running')"
        )).scalars().all())


def run_due(engine: Engine, *, batch_size: int = 25,
            fetcher_factory: Callable[[], Any] | None = None,
            now: dt.datetime | None = None) -> dict[str, Any]:
    """Advance every active backfill by one downloaded batch. Returns a per-format summary. Safe to call
    on every worker tick: a paused/cancelled/completed backfill is skipped by :func:`run_batch`."""
    make = fetcher_factory or dl.make_fetcher
    ran: list[dict[str, Any]] = []
    for wid in _active_workspaces(engine):
        with workspace_transaction(engine, wid) as conn:
            for row in backfill.list_all(conn, wid):
                if row["status"] not in ("pending", "running"):
                    continue
                fmt = row["format"]
                try:
                    res = dl.fetch_bundle(fmt, fetcher=make())
                    if not res.ok:
                        conn.execute(text("UPDATE cricsheet_backfill SET last_error = :e, updated_at = now() "
                                          "WHERE id = :id"),
                                     {"e": f"download {res.outcome}: {res.detail}", "id": row["id"]})
                        ran.append({"workspace_id": str(wid), "format": fmt, "ran": False,
                                    "error": res.outcome})
                        continue
                    out = backfill.run_batch(conn, wid, SYSTEM_ACTOR, fmt, res.content or b"",
                                             batch_size=batch_size)
                    ran.append({"workspace_id": str(wid), "format": fmt, **out})
                except Exception as exc:  # noqa: BLE001 - isolate per workspace/format
                    conn.execute(text("UPDATE cricsheet_backfill SET last_error = :e, updated_at = now() "
                                      "WHERE id = :id"), {"e": str(exc), "id": row["id"]})
                    ran.append({"workspace_id": str(wid), "format": fmt, "ran": False, "error": str(exc)})
    return {"ticked": len(ran), "runs": ran}
