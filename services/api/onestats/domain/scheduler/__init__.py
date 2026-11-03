"""Recurring, timezone-aware scheduled tasks for OneStats.

A scheduled task is a persistent recurrence definition that, when due, enqueues a job for the
in-process background worker. The recurrence is computed in the task's IANA timezone so it stays
correct across daylight-saving transitions, and firing is honest about whether a run happened on time
or as a late catch-up (never pretending a powered-off computer ran on schedule).
"""
from __future__ import annotations

from onestats.domain.scheduler import recurrence, tasks

__all__ = ["recurrence", "tasks"]
