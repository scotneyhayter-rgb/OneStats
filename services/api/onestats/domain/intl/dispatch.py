"""Dispatcher for the International workspace's recurring update.

A scheduled task fires by calling its registered dispatcher. This module registers
``intl_weekly_update`` — the daily 04:00 Australia/Melbourne job that looks for newly completed /
recently corrected international matches via the Internet Research Engine. (The dispatcher KEY is kept
as ``intl_weekly_update`` for continuity with the existing task row and audit history; the cadence is
set by the ``scheduled_task`` schedule, now daily.)

The pipeline is WIRED: when the task fires, it enqueues a real, resumable research job (the same engine
the "Search the Internet" button uses) scoped to incremental international updates and constrained to
the agreed allow-list of sources (see :mod:`onestats.domain.intl.sources`). The background worker runs
that job; its findings are LEADS that still pass through the normal review/approval workflow —
NOTHING is auto-imported, and completeness is only ever claimed once reconciled across >= 2 sources.
The run log records the enqueued job id, so a run links to the work it started.

Honesty is preserved end to end: enqueuing a job is recorded as ``succeeded`` (a job really was
created); an already-running update is an honest ``skipped`` (no second job); and if the engine is
unavailable the run is recorded as ``no_pipeline`` rather than a fake success.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.engine import Connection

from onestats.domain.intl import sources
from onestats.domain.intl.match_index import FORMATS
from onestats.domain.scheduler import tasks

TASK_KIND = "intl_weekly_update"

# What the recurring job is asked to find. Plain-language query for the research engine; the structured
# scope/allow-list travels in the job context so retrieval stays on the agreed sources.
_UPDATE_QUERY = ("Newly completed or recently corrected men's international cricket matches "
                 "(Test, ODI and T20I) to add to or update the international match index.")


def _weekly_update_dispatcher(conn: Connection, workspace_id: UUID, actor: str,
                              task: dict[str, Any]) -> dict[str, Any]:
    """Enqueue the incremental-update research job for the International workspace.

    Reuses the research engine's job queue (``research_job``) via its public ``create_job`` entrypoint,
    so there is no duplicate retrieval/extraction code here. The job context carries the explicit scope
    and the fetch allow-list; the engine's worker then retrieves, extracts and files findings for review.
    Returns the new job id as ``enqueued_job_id`` so the scheduler run links to it.
    """
    try:
        from onestats.domain.research import jobs as research_jobs
    except ImportError:
        # The research engine is not present in this build — record the truth, never a fake import.
        return {
            "status": "no_pipeline",
            "detail": "update fired, but the research engine is not available in this build; "
                      "no job was enqueued. Recorded truthfully, not as a successful import.",
        }

    context = {
        "task": TASK_KIND,
        "scope": "updated",                       # incremental (new/changed matches), not a full backfill
        "formats": list(FORMATS),
        # Explicit allow-list: the engine must fetch only these hosts, and reconcile >= 2 before any
        # completeness is claimed. Benchmarks (ESPNcricinfo, CricketStatz) are never fetched.
        "allowed_sources": [s.host for s in sources.fetchable_sources()],
        "min_sources_for_completeness": sources.MIN_SOURCES_FOR_COMPLETENESS,
    }
    try:
        job = research_jobs.create_job(conn, workspace_id, actor, query=_UPDATE_QUERY,
                                       depth="standard", context=context)
    except ValueError as exc:
        if str(exc) == "duplicate_active_job":
            # A previous update is still running — do not stack a second one. Honest, not a failure.
            return {"status": "skipped",
                    "detail": "an international update job is already in progress; not starting another."}
        raise  # any other error is recorded as a genuine failure by the scheduler

    return {
        "status": "succeeded",
        "detail": "enqueued an incremental international-update research job. Findings are leads that "
                  "require review before anything is imported; completeness needs >= 2 sources.",
        "enqueued_job_id": job["id"],
    }


def register() -> None:
    """Register the update dispatcher. Idempotent; called at import time and safe to re-call."""
    tasks.register_dispatcher(TASK_KIND, _weekly_update_dispatcher)


register()
