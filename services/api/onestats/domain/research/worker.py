"""In-process background worker for the Internet Research Engine.

The packaged desktop backend has no external broker or scheduler, so research jobs run on a daemon
thread started at application startup (see ``onestats.main`` lifespan). The worker:

  * reconciles stale jobs on start (a job left 'running' by a previous process whose lease expired is
    requeued or failed — never left falsely running);
  * polls each workspace for the next claimable job, claims it under a lease, and drives it step by step;
  * heartbeats between steps and re-reads the job status so a user's pause/cancel takes effect at the
    next page boundary (with the frontier safely checkpointed);
  * isolates every database operation inside a ``workspace_transaction`` (FORCE RLS), and never lets a
    single job's failure stop the loop.

Only ONE instance runs per process. It is started only when a database is configured, so the test
client (no DB) never launches it. Set ``ONESTATS_RESEARCH_WORKER=0`` to disable it.
"""
from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from onestats.core.config import Settings
from onestats.db.workspace import workspace_transaction
from onestats.domain.research import engine as research_engine
from onestats.domain.research import jobs

log = logging.getLogger("onestats.research.worker")

SYSTEM_ACTOR = "00000000-0000-0000-0000-000000000000"


def _list_workspace_ids(engine: Engine) -> list[str]:
    """All workspace ids (the registry is global, not RLS-scoped)."""
    with engine.begin() as conn:
        return [str(r[0]) for r in conn.execute(text("SELECT id FROM workspace")).all()]


class ResearchWorker:
    def __init__(self, engine: Engine, settings: Settings, *, poll_seconds: float = 3.0,
                 step_pause_seconds: float = 0.0) -> None:
        self._engine = engine
        self._settings = settings
        self._poll = poll_seconds
        self._step_pause = step_pause_seconds
        self._owner = f"research-worker-{uuid.uuid4().hex[:12]}"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._reconciled = False

    # -- lifecycle ----------------------------------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="research-worker", daemon=True)
        self._thread.start()
        log.info("Research worker started (owner=%s).", self._owner)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    # -- main loop ----------------------------------------------------------------------------------
    def _loop(self) -> None:
        while not self._stop.is_set():
            did_work = False
            try:
                workspace_ids = _list_workspace_ids(self._engine)
            except Exception as exc:  # noqa: BLE001 - DB hiccup: back off and retry
                log.warning("Research worker could not list workspaces: %s", type(exc).__name__)
                self._stop.wait(self._poll)
                continue
            if not self._reconciled:
                for wsid in workspace_ids:
                    self._safe_reconcile(wsid)
                self._reconciled = True
            for wsid in workspace_ids:
                if self._stop.is_set():
                    break
                try:
                    if self._run_next_for_workspace(wsid):
                        did_work = True
                except Exception as exc:
                    log.exception("Research worker error in workspace %s: %s", wsid, type(exc).__name__)

            # Scheduler tick (shared single thread, coordinated with the International workspace session):
            # fire any due scheduled tasks across workspaces. Cheap, idempotent and due-gated — a past-due
            # task fires once on the next tick (incl. the first tick after the PC powers back on). It must
            # never stop the research loop, so its failure is logged and swallowed.
            self._scheduler_tick()

            # Cricsheet backfill tick (International workspace): download + import one bounded batch per
            # active backfill. It does network I/O, so it belongs on the worker (not a request/scheduler
            # txn); due-gated, idempotent, failure-isolated per workspace/format, and a no-op when nothing
            # is active. Its failure must never stop the research loop.
            self._cricsheet_tick()

            if not did_work:
                self._stop.wait(self._poll)

    def _scheduler_tick(self) -> None:
        try:
            from onestats.domain.scheduler import worker as scheduler_worker

            scheduler_worker.tick_all_workspaces(self._engine)
        except Exception as exc:  # noqa: BLE001 - scheduler tick must never stop the research loop
            log.warning("Scheduler tick failed: %s", type(exc).__name__)

    def _cricsheet_tick(self) -> None:
        try:
            from onestats.domain.intl import cricsheet_worker

            cricsheet_worker.run_due(self._engine)
        except Exception as exc:  # noqa: BLE001 - cricsheet tick must never stop the research loop
            log.warning("Cricsheet tick failed: %s", type(exc).__name__)

    def _safe_reconcile(self, wsid: str) -> None:
        try:
            with workspace_transaction(self._engine, wsid) as conn:
                jobs.reconcile_stale_jobs(conn, uuid_of(wsid), SYSTEM_ACTOR)
        except Exception as exc:  # noqa: BLE001
            log.warning("Reconcile failed for workspace %s: %s", wsid, type(exc).__name__)

    def _run_next_for_workspace(self, wsid: str) -> bool:
        """Claim and run (to completion, or until paused/cancelled) the next job for one workspace.
        Returns True if a job was claimed."""
        with workspace_transaction(self._engine, wsid) as conn:
            claimed = jobs.claim_next_job(conn, uuid_of(wsid), self._owner)
        if claimed is None:
            return False
        job_id = claimed["id"]
        log.info("Research worker running job %s (workspace %s).", job_id, wsid)
        self._drive_job(wsid, job_id)
        return True

    def _drive_job(self, wsid: str, job_id: Any) -> None:
        guard = 0
        while not self._stop.is_set():
            guard += 1
            if guard > 10_000:  # defensive: never spin forever
                log.error("Research job %s exceeded step guard; stopping.", job_id)
                return
            try:
                with workspace_transaction(self._engine, wsid) as conn:
                    job = jobs.get_job(conn, job_id)
                    if job is None or job["status"] != "running":
                        return  # paused / cancelled / gone — stop, state already persisted
                    result = research_engine.run_step(conn, uuid_of(wsid), self._owner, job,
                                                       settings=self._settings)
                    jobs.heartbeat(conn, job_id)
                    if result["done"]:
                        jobs.complete_job(conn, uuid_of(wsid), self._owner, job_id,
                                          progress={"phase": "complete",
                                                    "sources_examined": result["examined"],
                                                    "findings": result["findings"]})
                        return
            except Exception as exc:
                log.exception("Research job %s step failed: %s", job_id, type(exc).__name__)
                try:
                    with workspace_transaction(self._engine, wsid) as conn:
                        jobs.fail_job(conn, uuid_of(wsid), self._owner, job_id, error=str(exc))
                except Exception as inner:  # noqa: BLE001 - failure already logged; avoid masking it
                    log.warning("Could not record failure for job %s: %s", job_id, type(inner).__name__)
                return
            if self._step_pause:
                self._stop.wait(self._step_pause)


def uuid_of(wsid: str):
    """Workspace ids come back as strings from the registry query; SQL binds accept the string, but
    keep a single helper so intent is clear."""
    return wsid


# -- module-level singleton management (used by the app lifespan) --------------------------------------
_worker: ResearchWorker | None = None


def start_worker(engine: Engine, settings: Settings) -> ResearchWorker | None:
    """Start the singleton worker if enabled and a database is configured. Returns the worker or None."""
    global _worker
    import os

    if os.environ.get("ONESTATS_RESEARCH_WORKER", "1") == "0":
        log.info("Research worker disabled by ONESTATS_RESEARCH_WORKER=0.")
        return None
    if engine is None:
        return None
    if _worker is not None:
        return _worker
    _worker = ResearchWorker(engine, settings)
    _worker.start()
    return _worker


def stop_worker() -> None:
    global _worker
    if _worker is not None:
        _worker.stop()
        _worker = None
