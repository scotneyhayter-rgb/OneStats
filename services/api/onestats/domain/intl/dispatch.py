"""Dispatcher for the International workspace's recurring weekly update.

A scheduled task fires by calling its registered dispatcher. This module registers
``intl_weekly_update`` — the Saturday 04:00 Australia/Melbourne job that pulls newly completed /
recently updated international matches via the Internet Research Engine.

The import pipeline (Parts D–G) is BLOCKED ON the research engine's retrieval/extraction/findings
machinery. Until that is wired, the dispatcher records an HONEST ``no_pipeline`` run — it does NOT
fabricate an import or claim matches were fetched. When the engine import lands, this is the single
place that enqueues the real "updated" research job; the scheduler, run history and UI need no change.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.engine import Connection

from onestats.domain.scheduler import tasks

TASK_KIND = "intl_weekly_update"


def _weekly_update_dispatcher(conn: Connection, workspace_id: UUID, actor: str,
                              task: dict[str, Any]) -> dict[str, Any]:
    """Enqueue the weekly incremental-update research job for the International workspace.

    Placeholder until the engine import pipeline is available: returns ``no_pipeline`` so the run log
    truthfully shows the task fired but had nothing to run yet. Replace the body with a call that
    enqueues an "updated"-scope research job (reusing the engine) and return its id as
    ``enqueued_job_id`` — no other part of the scheduler needs to change.
    """
    return {
        "status": "no_pipeline",
        "detail": "weekly update fired; import pipeline not yet wired to the research engine "
                  "(Parts D–G). No matches were fetched — this is recorded truthfully, not as a "
                  "successful import.",
    }


def register() -> None:
    """Register the weekly-update dispatcher. Idempotent; called at import time and safe to re-call."""
    tasks.register_dispatcher(TASK_KIND, _weekly_update_dispatcher)


register()
