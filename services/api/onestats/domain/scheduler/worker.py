"""Scheduler tick entry points for the in-process background worker.

The packaged desktop backend runs ONE background daemon thread (the Internet Research Engine's
``research.worker``). Rather than start a second competing thread, the scheduler exposes a cheap,
idempotent tick that that worker calls once per poll:

    from onestats.domain.scheduler import worker as scheduler_worker
    scheduler_worker.tick_all_workspaces(engine, now=None)   # inside the worker's loop

``tick_all_workspaces`` iterates every workspace and fires any due scheduled task (which includes the
missed-run catch-up: a task whose ``next_run_at`` is in the past simply fires once on the next tick,
whether that is the normal Saturday tick or the first tick after the PC is turned back on). Each
workspace runs in its own ``workspace_transaction`` (FORCE RLS), and one workspace's error never stops
the others. It is safe to call concurrently with the research worker — due-claiming uses row locks.
"""
from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

from onestats.db.workspace import workspace_transaction
from onestats.domain.intl import dispatch as intl_dispatch  # registers the intl weekly dispatcher
from onestats.domain.scheduler import tasks

log = logging.getLogger("onestats.scheduler.worker")

SYSTEM_ACTOR = "00000000-0000-0000-0000-000000000000"

# Ensure dispatchers are registered in this process even if nothing else imported them.
intl_dispatch.register()


def _workspace_ids(engine: Engine) -> list[str]:
    with engine.begin() as conn:
        return [str(r[0]) for r in conn.execute(text("SELECT id FROM workspace")).all()]


def tick_all_workspaces(engine: Engine, *, now: dt.datetime | None = None) -> dict[str, int]:
    """Fire every due scheduled task across all workspaces. Returns totals for logging. Never raises
    for a single workspace's failure."""
    now = now or dt.datetime.now(dt.timezone.utc)
    total_ran = 0
    workspaces = 0
    for wsid in _workspace_ids(engine):
        try:
            with workspace_transaction(engine, wsid) as conn:
                result = tasks.run_due(conn, wsid, SYSTEM_ACTOR, now=now)
            total_ran += result["ran"]
            if result["ran"]:
                workspaces += 1
        except Exception as exc:  # noqa: BLE001 - one workspace's failure must not stop the rest
            log.warning("Scheduler tick failed for workspace %s: %s", wsid, type(exc).__name__)
    return {"ran": total_ran, "workspaces": workspaces}
