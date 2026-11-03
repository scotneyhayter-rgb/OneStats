"""The international update dispatcher actually enqueues a research job (pipeline wired).

DB-backed, rolled back; skipped without a live DB. Proves: firing the daily task creates a real
``research_job`` scoped to the agreed allow-list and records the run as ``succeeded`` with the job id;
a second fire while that job is still active is an honest ``skipped`` (no duplicate job), never a fake
success; nothing is imported (findings go through review).
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.intl import dispatch as intl_dispatch
from onestats.domain.intl import sources
from onestats.domain.research import jobs as research_jobs
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


def _ws(conn):
    wid = conn.execute(text("INSERT INTO workspace(name, type) VALUES ('INTL DISPATCH','international') RETURNING id")).scalar_one()
    conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a,'disp') ON CONFLICT (id) DO NOTHING"), {"a": ACTOR})
    set_workspace(conn, wid)
    return wid


def _task(conn, wid):
    intl_dispatch.register()  # idempotent
    return tasks.upsert_daily(conn, wid, ACTOR, name="Daily international update",
                              task_kind=intl_dispatch.TASK_KIND, tz="Australia/Melbourne",
                              hour=4, minute=0, now=dt.datetime(2026, 7, 6, 0, 0, tzinfo=UTC))


def test_fire_enqueues_a_research_job_on_the_allow_list(conn):
    wid = _ws(conn)
    t = _task(conn, wid)
    out = tasks.run_now(conn, wid, ACTOR, t["id"])
    assert out["status"] == "succeeded"

    # a real research job now exists
    jobs = research_jobs.list_jobs(conn, wid)
    assert len(jobs) == 1
    job = jobs[0]
    assert job["status"] in ("pending", "running")       # queued for the worker, not auto-completed
    ctx = job["context"]
    assert ctx["scope"] == "updated" and set(ctx["formats"]) == {"test", "odi", "t20i"}
    # constrained to the agreed fetch allow-list — benchmarks (espncricinfo/cricketstatz) are NOT here
    allowed = set(ctx["allowed_sources"])
    assert allowed == {s.host for s in sources.fetchable_sources()}
    assert "espncricinfo.com" not in allowed

    # the run row links to the enqueued job and is recorded as a genuine success
    run = tasks.list_runs(conn, wid)[0]
    assert run["status"] == "succeeded" and str(run["enqueued_job_id"]) == str(job["id"])


def test_second_fire_while_active_is_skipped_not_duplicated(conn):
    wid = _ws(conn)
    t = _task(conn, wid)
    tasks.run_now(conn, wid, ACTOR, t["id"])
    second = tasks.run_now(conn, wid, ACTOR, t["id"])
    assert second["status"] == "skipped"
    # still exactly ONE job — the active one was not duplicated
    assert len(research_jobs.list_jobs(conn, wid)) == 1
    runs = tasks.list_runs(conn, wid)
    assert [r["status"] for r in runs[:2]] == ["skipped", "succeeded"]  # newest first
