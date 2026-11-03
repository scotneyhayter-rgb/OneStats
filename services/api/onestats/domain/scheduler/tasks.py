"""Scheduled-task persistence, due-claiming, dispatch and honest run recording.

The background worker calls :func:`run_due` on a tick and on startup. A due task (``next_run_at`` in
the past or present) is claimed with ``FOR UPDATE SKIP LOCKED`` — so two ticks never double-fire it —
then its dispatcher runs (typically enqueuing an import job), a :func:`scheduled_task_run` row records
what actually happened, and ``next_run_at`` is advanced to the next FUTURE occurrence. Advancing to the
next future occurrence (not the next missed one) means a long outage collapses to a SINGLE catch-up
run, never a backlog of retroactive runs, and a run is only ever recorded when it actually executes.
"""
from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit
from onestats.domain.scheduler import recurrence

# dispatcher registry: task_kind -> fn(conn, workspace_id, actor, task) -> dict
#   returns {"status": one of succeeded|failed|skipped|no_pipeline,
#            "detail"?: str, "error"?: str, "enqueued_job_id"?: UUID|str}
_DISPATCHERS: dict[str, Callable[..., dict[str, Any]]] = {}


def register_dispatcher(task_kind: str, fn: Callable[..., dict[str, Any]]) -> None:
    _DISPATCHERS[task_kind] = fn


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _row(conn: Connection, task_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text("SELECT * FROM scheduled_task WHERE id = :id"), {"id": task_id}).mappings().first()
    return dict(r) if r else None


def upsert_weekly(
    conn: Connection, workspace_id: UUID, actor: str, *, name: str, task_kind: str, tz: str,
    day_of_week: int, hour: int, minute: int, payload: dict[str, Any] | None = None,
    catch_up: bool = True, now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Create or update the single WEEKLY task of ``task_kind`` for a workspace (idempotent)."""
    return _upsert(conn, workspace_id, actor, name=name, task_kind=task_kind, tz=tz,
                   schedule_kind="weekly", day_of_week=day_of_week, hour=hour, minute=minute,
                   payload=payload, catch_up=catch_up, now=now)


def upsert_daily(
    conn: Connection, workspace_id: UUID, actor: str, *, name: str, task_kind: str, tz: str,
    hour: int, minute: int, payload: dict[str, Any] | None = None,
    catch_up: bool = True, now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Create or update the single DAILY task of ``task_kind`` for a workspace (idempotent). Switching
    an existing weekly task to daily (or vice versa) is detected as a schedule change and recomputes
    ``next_run_at`` while preserving ``last_run_at``/run history."""
    return _upsert(conn, workspace_id, actor, name=name, task_kind=task_kind, tz=tz,
                   schedule_kind="daily", day_of_week=None, hour=hour, minute=minute,
                   payload=payload, catch_up=catch_up, now=now)


def _upsert(
    conn: Connection, workspace_id: UUID, actor: str, *, name: str, task_kind: str, tz: str,
    schedule_kind: str, day_of_week: int | None, hour: int, minute: int,
    payload: dict[str, Any] | None, catch_up: bool, now: dt.datetime | None,
) -> dict[str, Any]:
    """Create or update the single task of ``task_kind`` for a workspace (idempotent). The recurrence
    fields are always updated; ``next_run_at`` is (re)computed from ``now`` whenever it is unset or the
    schedule changed, and ``last_run_at``/history are preserved."""
    now = now or _utcnow()
    nxt = recurrence.next_occurrence(now, schedule_kind=schedule_kind, day_of_week=day_of_week,
                                     hour=hour, minute=minute, tz=tz)
    existing = conn.execute(
        text("SELECT id, schedule_kind, day_of_week, hour, minute, timezone FROM scheduled_task "
             "WHERE workspace_id = :w AND task_kind = :k"),
        {"w": workspace_id, "k": task_kind},
    ).mappings().first()
    pj = json.dumps(payload) if payload is not None else None
    if existing is None:
        tid = conn.execute(
            text("INSERT INTO scheduled_task(workspace_id, name, task_kind, payload, timezone, "
                 "schedule_kind, day_of_week, hour, minute, catch_up, next_run_at, created_by) "
                 "VALUES (:w, :n, :k, CAST(:p AS jsonb), :tz, :sk, :dow, :h, :m, :cu, :nxt, :by) "
                 "RETURNING id"),
            {"w": workspace_id, "n": name, "k": task_kind, "p": pj, "tz": tz, "sk": schedule_kind,
             "dow": day_of_week, "h": hour, "m": minute, "cu": catch_up, "nxt": nxt, "by": actor},
        ).scalar_one()
        audit.write_audit(conn, workspace_id, actor, "scheduler.task_created", entity="scheduled_task",
                          entity_id=str(tid), after={"task_kind": task_kind, "timezone": tz,
                                                     "schedule_kind": schedule_kind,
                                                     "day_of_week": day_of_week, "hour": hour,
                                                     "minute": minute})
        return _row(conn, tid)  # type: ignore[return-value]
    schedule_changed = (existing["schedule_kind"] != schedule_kind
                        or existing["day_of_week"] != day_of_week or existing["hour"] != hour
                        or existing["minute"] != minute or existing["timezone"] != tz)
    conn.execute(
        text("UPDATE scheduled_task SET name = :n, payload = CAST(:p AS jsonb), timezone = :tz, "
             "schedule_kind = :sk, day_of_week = :dow, hour = :h, minute = :m, catch_up = :cu, "
             "next_run_at = CASE WHEN next_run_at IS NULL OR :changed THEN :nxt ELSE next_run_at END, "
             "updated_at = now() WHERE id = :id"),
        {"n": name, "p": pj, "tz": tz, "sk": schedule_kind, "dow": day_of_week, "h": hour, "m": minute,
         "cu": catch_up, "changed": schedule_changed, "nxt": nxt, "id": existing["id"]},
    )
    return _row(conn, existing["id"])  # type: ignore[return-value]


def get_task(conn: Connection, workspace_id: UUID, task_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(
        text("SELECT * FROM scheduled_task WHERE id = :id AND workspace_id = :w"),
        {"id": task_id, "w": workspace_id},
    ).mappings().first()
    return dict(r) if r else None


def list_tasks(conn: Connection, workspace_id: UUID) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        text("SELECT * FROM scheduled_task WHERE workspace_id = :w ORDER BY name"),
        {"w": workspace_id}).mappings().all()]


def list_runs(conn: Connection, workspace_id: UUID, *, task_id: UUID | None = None,
              limit: int = 50) -> list[dict[str, Any]]:
    sql = "SELECT * FROM scheduled_task_run WHERE workspace_id = :w"
    params: dict[str, Any] = {"w": workspace_id, "lim": limit}
    if task_id is not None:
        sql += " AND task_id = :t"
        params["t"] = task_id
    sql += " ORDER BY ran_at DESC LIMIT :lim"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def set_enabled(conn: Connection, workspace_id: UUID, actor: str, task_id: UUID, enabled: bool) -> dict[str, Any]:
    conn.execute(text("UPDATE scheduled_task SET enabled = :e, updated_at = now() "
                      "WHERE id = :id AND workspace_id = :w"),
                 {"e": enabled, "id": task_id, "w": workspace_id})
    audit.write_audit(conn, workspace_id, actor, "scheduler.task_enabled", entity="scheduled_task",
                      entity_id=str(task_id), after={"enabled": enabled})
    return get_task(conn, workspace_id, task_id)  # type: ignore[return-value]


def set_paused(conn: Connection, workspace_id: UUID, actor: str, task_id: UUID, paused: bool) -> dict[str, Any]:
    conn.execute(text("UPDATE scheduled_task SET paused = :p, updated_at = now() "
                      "WHERE id = :id AND workspace_id = :w"),
                 {"p": paused, "id": task_id, "w": workspace_id})
    audit.write_audit(conn, workspace_id, actor, "scheduler.task_paused", entity="scheduled_task",
                      entity_id=str(task_id), after={"paused": paused})
    return get_task(conn, workspace_id, task_id)  # type: ignore[return-value]


def _record_run(conn: Connection, workspace_id: UUID, task_id: UUID, *, scheduled_for: dt.datetime | None,
                ran_at: dt.datetime, was_catch_up: bool, status: str, detail: str | None = None,
                error: str | None = None, enqueued_job_id: Any = None) -> None:
    conn.execute(
        text("INSERT INTO scheduled_task_run(workspace_id, task_id, scheduled_for, ran_at, was_catch_up, "
             "status, detail, error, enqueued_job_id) "
             "VALUES (:w, :t, :sf, :ra, :cu, :st, :d, :e, :jid)"),
        {"w": workspace_id, "t": task_id, "sf": scheduled_for, "ra": ran_at, "cu": was_catch_up,
         "st": status, "d": detail, "e": error, "jid": enqueued_job_id},
    )


def _dispatch_one(conn: Connection, workspace_id: UUID, actor: str, task: dict[str, Any],
                  *, now: dt.datetime, user_initiated: bool = False) -> dict[str, Any]:
    """Run one already-claimed task: honour the catch-up policy, dispatch (or skip), record a genuine
    run row, and advance ``next_run_at`` to the next future occurrence."""
    scheduled_for = task["next_run_at"]
    was_catch_up = (not user_initiated) and recurrence.is_catch_up(scheduled_for, now)

    if was_catch_up and not task["catch_up"]:
        # A missed occurrence that the task is configured NOT to catch up on: record it as skipped
        # (so the history is honest that the occurrence was missed), dispatch nothing.
        result = {"status": "skipped", "detail": "missed while powered off; catch-up disabled"}
    else:
        dispatcher = _DISPATCHERS.get(task["task_kind"])
        if dispatcher is None:
            result = {"status": "failed", "error": f"no dispatcher for task_kind '{task['task_kind']}'"}
        else:
            try:
                result = dispatcher(conn, workspace_id, actor, task) or {"status": "succeeded"}
            except Exception as exc:  # noqa: BLE001 - any dispatcher error becomes a recorded failure
                result = {"status": "failed", "error": str(exc)}

    _record_run(conn, workspace_id, task["id"], scheduled_for=scheduled_for, ran_at=now,
                was_catch_up=was_catch_up, status=result["status"], detail=result.get("detail"),
                error=result.get("error"), enqueued_job_id=result.get("enqueued_job_id"))

    nxt = recurrence.next_occurrence(now, schedule_kind=task["schedule_kind"],
                                     day_of_week=task["day_of_week"], hour=task["hour"],
                                     minute=task["minute"], tz=task["timezone"])
    conn.execute(
        text("UPDATE scheduled_task SET next_run_at = :nxt, last_run_at = :now, last_status = :st, "
             "last_error = :err, updated_at = now() WHERE id = :id"),
        {"nxt": nxt, "now": now, "st": result["status"], "err": result.get("error"), "id": task["id"]},
    )
    return {"task_id": str(task["id"]), "status": result["status"], "was_catch_up": was_catch_up,
            "scheduled_for": scheduled_for.isoformat() if scheduled_for else None}


def run_due(conn: Connection, workspace_id: UUID, actor: str, *, now: dt.datetime | None = None,
            max_tasks: int = 20) -> dict[str, Any]:
    """Claim and run every due task for a workspace (the worker's tick; also the startup catch-up pass).
    Each task is claimed under a row lock so a concurrent tick cannot double-fire it."""
    now = now or _utcnow()
    ran: list[dict[str, Any]] = []
    while len(ran) < max_tasks:
        task = conn.execute(
            text("SELECT * FROM scheduled_task WHERE workspace_id = :w AND enabled AND NOT paused "
                 "AND next_run_at IS NOT NULL AND next_run_at <= :now "
                 "ORDER BY next_run_at FOR UPDATE SKIP LOCKED LIMIT 1"),
            {"w": workspace_id, "now": now},
        ).mappings().first()
        if task is None:
            break
        ran.append(_dispatch_one(conn, workspace_id, actor, dict(task), now=now))
    return {"ran": len(ran), "runs": ran}


def run_now(conn: Connection, workspace_id: UUID, actor: str, task_id: UUID, *,
            now: dt.datetime | None = None) -> dict[str, Any]:
    """"Update Now": run one task immediately regardless of its schedule (user-initiated, so never
    recorded as a catch-up). Advances ``next_run_at`` to the next future occurrence as usual."""
    now = now or _utcnow()
    task = conn.execute(
        text("SELECT * FROM scheduled_task WHERE id = :id AND workspace_id = :w FOR UPDATE"),
        {"id": task_id, "w": workspace_id},
    ).mappings().first()
    if task is None:
        raise ValueError("task_not_found")
    audit.write_audit(conn, workspace_id, actor, "scheduler.run_now", entity="scheduled_task",
                      entity_id=str(task_id))
    return _dispatch_one(conn, workspace_id, actor, dict(task), now=now, user_initiated=True)
