"""Scheduled-task persistence, due-claiming and HONEST run recording — DB-backed.

Rolled back per test; skipped without a live DB. Covers: idempotent weekly upsert, a due task firing
exactly once, a long outage collapsing to a single catch-up run (never a retroactive backlog, never a
fabricated on-time run), two ticks not double-firing, the catch-up=off policy skipping a missed
occurrence, user-initiated run-now never being mislabelled a catch-up, and workspace isolation.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.scheduler import tasks

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "11111111-1111-1111-1111-111111111111"
UTC = dt.timezone.utc


@pytest.fixture
def conn():
    eng = create_engine(settings.database_url, future=True)
    with eng.connect() as c:
        trans = c.begin()
        try:
            yield c
        finally:
            trans.rollback()
    eng.dispose()


@pytest.fixture
def counting_dispatcher():
    calls: list[dict] = []

    def _fn(conn, workspace_id, actor, task):
        calls.append({"task_id": str(task["id"])})
        return {"status": "succeeded", "detail": f"call {len(calls)}"}

    tasks.register_dispatcher("test_weekly", _fn)
    return calls


def _ws(conn, name):
    wid = conn.execute(text("INSERT INTO workspace(name, type) VALUES (:n,'international') RETURNING id"),
                       {"n": name}).scalar_one()
    conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a, :u) ON CONFLICT (id) DO NOTHING"),
                 {"a": ACTOR, "u": f"actor-{name}"})
    set_workspace(conn, wid)
    return wid


def _mk(conn, wid, *, catch_up=True, now):
    return tasks.upsert_weekly(conn, wid, ACTOR, name="Weekly update", task_kind="test_weekly",
                               tz="Australia/Melbourne", day_of_week=5, hour=4, minute=0,
                               catch_up=catch_up, now=now)


def _mk_daily(conn, wid, *, now):
    return tasks.upsert_daily(conn, wid, ACTOR, name="Daily update", task_kind="test_weekly",
                              tz="Australia/Melbourne", hour=4, minute=0, now=now)


def test_daily_task_fires_and_advances_one_day(conn, counting_dispatcher):
    wid = _ws(conn, "SCHED DAILY")
    created = dt.datetime(2026, 7, 6, 0, 0, tzinfo=UTC)
    t = _mk_daily(conn, wid, now=created)
    # created on Mon 06:00 local -> first run is 2026-07-07 04:00 AEST == 2026-07-06 18:00Z
    assert t["schedule_kind"] == "daily" and t["day_of_week"] is None
    assert t["next_run_at"] == dt.datetime(2026, 7, 6, 18, 0, tzinfo=UTC)
    res = tasks.run_due(conn, wid, ACTOR, now=dt.datetime(2026, 7, 6, 18, 0, tzinfo=UTC))
    assert res["ran"] == 1 and len(counting_dispatcher) == 1
    # advances exactly ONE day, still 04:00 local
    nxt = tasks.list_tasks(conn, wid)[0]["next_run_at"]
    assert nxt == dt.datetime(2026, 7, 7, 18, 0, tzinfo=UTC)


def test_switch_weekly_to_daily_recomputes_next_run(conn):
    wid = _ws(conn, "SCHED SWITCH")
    now = dt.datetime(2026, 7, 6, 0, 0, tzinfo=UTC)  # Monday
    wk = _mk(conn, wid, now=now)
    assert wk["schedule_kind"] == "weekly"
    assert wk["next_run_at"] == dt.datetime(2026, 7, 10, 18, 0, tzinfo=UTC)  # Saturday
    dy = _mk_daily(conn, wid, now=now)  # same task_kind -> updates in place
    assert dy["id"] == wk["id"] and len(tasks.list_tasks(conn, wid)) == 1
    assert dy["schedule_kind"] == "daily" and dy["day_of_week"] is None
    # schedule changed -> next_run_at recomputed to the next daily 04:00 (that same evening UTC)
    assert dy["next_run_at"] == dt.datetime(2026, 7, 6, 18, 0, tzinfo=UTC)


def test_upsert_is_idempotent_and_sets_next_run(conn):
    wid = _ws(conn, "SCHED UPSERT")
    now = dt.datetime(2026, 7, 6, 0, 0, tzinfo=UTC)
    t1 = _mk(conn, wid, now=now)
    assert t1["next_run_at"] == dt.datetime(2026, 7, 10, 18, 0, tzinfo=UTC)
    t2 = _mk(conn, wid, now=now)  # second call must not create a duplicate
    assert t2["id"] == t1["id"]
    assert len(tasks.list_tasks(conn, wid)) == 1


def test_due_task_fires_once_and_advances(conn, counting_dispatcher):
    wid = _ws(conn, "SCHED FIRE")
    created_now = dt.datetime(2026, 7, 6, 0, 0, tzinfo=UTC)
    _mk(conn, wid, now=created_now)
    # tick at the scheduled instant
    fire_now = dt.datetime(2026, 7, 10, 18, 0, tzinfo=UTC)
    res = tasks.run_due(conn, wid, ACTOR, now=fire_now)
    assert res["ran"] == 1 and len(counting_dispatcher) == 1
    runs = tasks.list_runs(conn, wid)
    assert len(runs) == 1
    assert runs[0]["status"] == "succeeded"
    assert runs[0]["scheduled_for"] == dt.datetime(2026, 7, 10, 18, 0, tzinfo=UTC)
    assert runs[0]["was_catch_up"] is False
    # next_run_at advanced to the following Saturday
    t = tasks.list_tasks(conn, wid)[0]
    assert t["next_run_at"] == dt.datetime(2026, 7, 17, 18, 0, tzinfo=UTC)


def test_missed_occurrences_collapse_to_single_catch_up(conn, counting_dispatcher):
    wid = _ws(conn, "SCHED CATCHUP")
    # created long ago; the scheduled instant is weeks in the past (PC was off)
    _mk(conn, wid, now=dt.datetime(2026, 6, 1, 0, 0, tzinfo=UTC))
    now = dt.datetime(2026, 7, 20, 9, 0, tzinfo=UTC)  # startup weeks later
    res = tasks.run_due(conn, wid, ACTOR, now=now)
    # fires exactly ONCE, not once per missed week
    assert res["ran"] == 1 and len(counting_dispatcher) == 1
    runs = tasks.list_runs(conn, wid)
    assert len(runs) == 1 and runs[0]["was_catch_up"] is True
    # ran_at is the real (late) time, scheduled_for is the missed instant — never pretends on-time
    assert runs[0]["ran_at"] == now
    assert runs[0]["scheduled_for"] < now
    # next occurrence is in the FUTURE relative to now
    assert tasks.list_tasks(conn, wid)[0]["next_run_at"] > now


def test_two_ticks_do_not_double_fire(conn, counting_dispatcher):
    wid = _ws(conn, "SCHED NODOUBLE")
    _mk(conn, wid, now=dt.datetime(2026, 7, 6, 0, 0, tzinfo=UTC))
    now = dt.datetime(2026, 7, 10, 18, 0, tzinfo=UTC)
    tasks.run_due(conn, wid, ACTOR, now=now)
    second = tasks.run_due(conn, wid, ACTOR, now=now)  # same instant, immediately after
    assert second["ran"] == 0 and len(counting_dispatcher) == 1


def test_catch_up_disabled_skips_missed_occurrence(conn, counting_dispatcher):
    wid = _ws(conn, "SCHED NOCATCHUP")
    _mk(conn, wid, catch_up=False, now=dt.datetime(2026, 6, 1, 0, 0, tzinfo=UTC))
    now = dt.datetime(2026, 7, 20, 9, 0, tzinfo=UTC)
    res = tasks.run_due(conn, wid, ACTOR, now=now)
    assert res["ran"] == 1  # the occurrence was processed...
    assert len(counting_dispatcher) == 0  # ...but NOT dispatched
    runs = tasks.list_runs(conn, wid)
    assert runs[0]["status"] == "skipped" and runs[0]["was_catch_up"] is True


def test_run_now_is_never_a_catch_up(conn, counting_dispatcher):
    wid = _ws(conn, "SCHED RUNNOW")
    t = _mk(conn, wid, now=dt.datetime(2026, 6, 1, 0, 0, tzinfo=UTC))  # next_run far in past
    now = dt.datetime(2026, 7, 20, 9, 0, tzinfo=UTC)
    out = tasks.run_now(conn, wid, ACTOR, t["id"], now=now)
    assert out["status"] == "succeeded" and out["was_catch_up"] is False
    assert len(counting_dispatcher) == 1


def test_missing_dispatcher_records_failure(conn):
    wid = _ws(conn, "SCHED NODISP")
    tasks.upsert_weekly(conn, wid, ACTOR, name="Orphan", task_kind="test_no_dispatcher_registered",
                        tz="Australia/Melbourne", day_of_week=5, hour=4, minute=0,
                        now=dt.datetime(2026, 7, 6, 0, 0, tzinfo=UTC))
    tasks.run_due(conn, wid, ACTOR, now=dt.datetime(2026, 7, 10, 18, 0, tzinfo=UTC))
    runs = tasks.list_runs(conn, wid)
    assert runs[0]["status"] == "failed" and "no dispatcher" in (runs[0]["error"] or "")


def test_workspace_isolation(conn, counting_dispatcher):
    wid_a = _ws(conn, "SCHED ISO A")
    _mk(conn, wid_a, now=dt.datetime(2026, 7, 6, 0, 0, tzinfo=UTC))
    wid_b = _ws(conn, "SCHED ISO B")  # set_workspace now points at B
    # B sees none of A's tasks under RLS
    assert tasks.list_tasks(conn, wid_b) == []
    # running due tasks for B does not touch A's task
    tasks.run_due(conn, wid_b, ACTOR, now=dt.datetime(2026, 7, 10, 18, 0, tzinfo=UTC))
    assert len(counting_dispatcher) == 0
