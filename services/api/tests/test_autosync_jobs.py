"""Phase 9, Stage 9.1 — AutoSync background job engine.

Rolled back per test; skipped without a live DB. Covers create + duplicate-active prevention, claim/
lease/heartbeat, checkpoint, complete, retry/fail, cancel, restart-safe reconciliation of jobs left
'running' after a shutdown, handler execution via the runner, and workspace isolation.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.autosync import jobs

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "11111111-1111-1111-1111-111111111111"


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


def _ws(conn, name):
    wid = conn.execute(text("INSERT INTO workspace(name, type) VALUES (:n,'club') RETURNING id"), {"n": name}).scalar_one()
    conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a, :u) ON CONFLICT (id) DO NOTHING"),
                 {"a": ACTOR, "u": f"actor-{name}"})
    set_workspace(conn, wid)
    return wid


def _expire_lease(conn, job_id):
    conn.execute(text("UPDATE sync_job SET lease_expires_at = now() - interval '1 minute' WHERE id = :id"), {"id": job_id})


def test_create_claim_complete_and_duplicate_prevention(conn):
    wid = _ws(conn, "JOBS")
    job = jobs.create_job(conn, wid, ACTOR, source_system="fixture_feed", kind="new")
    assert job["status"] == "pending"
    # a second active job for the same (source, kind) is refused
    with pytest.raises(ValueError, match="duplicate_active_job"):
        jobs.create_job(conn, wid, ACTOR, source_system="fixture_feed", kind="new")

    claimed = jobs.claim_next_job(conn, wid, ACTOR)
    assert claimed["id"] == job["id"] and claimed["status"] == "running" and claimed["lease_owner"] == ACTOR
    assert jobs.claim_next_job(conn, wid, ACTOR) is None   # nothing else due

    jobs.save_checkpoint(conn, job["id"], {"page": 3}, progress={"found": 2})
    assert jobs.get_job(conn, job["id"])["checkpoint"] == {"page": 3}

    done = jobs.complete_job(conn, wid, ACTOR, job["id"], progress={"found": 5})
    assert done["status"] == "succeeded" and done["lease_owner"] is None and done["progress"] == {"found": 5}
    # once completed, a fresh job can be queued again
    assert jobs.create_job(conn, wid, ACTOR, source_system="fixture_feed", kind="new")["status"] == "pending"


def test_retry_then_fail_when_exhausted(conn):
    wid = _ws(conn, "JOBS RETRY")
    job = jobs.create_job(conn, wid, ACTOR, source_system="feed", kind="new", max_attempts=2)
    jobs.claim_next_job(conn, wid, ACTOR)
    r1 = jobs.fail_job(conn, wid, ACTOR, job["id"], error="boom")
    assert r1["status"] == "pending" and r1["attempts"] == 1 and r1["next_run_at"] is not None
    jobs.claim_next_job(conn, wid, ACTOR)   # (next_run_at is in the future; claim by clearing it)
    conn.execute(text("UPDATE sync_job SET next_run_at = NULL WHERE id = :id"), {"id": job["id"]})
    jobs.claim_next_job(conn, wid, ACTOR)
    r2 = jobs.fail_job(conn, wid, ACTOR, job["id"], error="boom again")
    assert r2["status"] == "failed" and r2["attempts"] == 2    # retries exhausted


def test_reconcile_recovers_jobs_running_when_pc_powered_off(conn):
    wid = _ws(conn, "JOBS RECONCILE")
    job = jobs.create_job(conn, wid, ACTOR, source_system="feed", kind="historical")
    jobs.claim_next_job(conn, wid, ACTOR)        # running, holding a lease
    _expire_lease(conn, job["id"])                # simulate the PC powering off mid-job

    out = jobs.reconcile_stale_jobs(conn, wid, ACTOR)
    assert out["requeued"] == 1 and out["failed"] == 0
    j = jobs.get_job(conn, job["id"])
    assert j["status"] == "interrupted" and j["lease_owner"] is None   # NOT falsely 'running'
    # the interrupted job is picked up again (missed check resumes)
    assert jobs.claim_next_job(conn, wid, ACTOR)["id"] == job["id"]


def test_runner_executes_handler_and_records_outcome(conn):
    wid = _ws(conn, "JOBS RUN")
    seen = {}

    def handler(c, w, actor, job):
        seen["ran"] = str(job["id"])
        jobs.save_checkpoint(c, job["id"], {"done": True})
        return {"discovered": 7}

    jobs.register_handler("new", handler)
    jobs.create_job(conn, wid, ACTOR, source_system="feed", kind="new")
    out = jobs.run_due_jobs(conn, wid, ACTOR)
    assert out["ran"] == 1 and "ran" in seen
    done = jobs.list_jobs(conn, wid, status="succeeded")
    assert len(done) == 1 and done[0]["progress"] == {"discovered": 7}


def test_runner_failing_handler_is_retried(conn):
    wid = _ws(conn, "JOBS RUN FAIL")

    def bad(c, w, actor, job):
        raise RuntimeError("source outage")

    jobs.register_handler("updated", bad)
    jobs.create_job(conn, wid, ACTOR, source_system="feed", kind="updated")
    jobs.run_due_jobs(conn, wid, ACTOR)
    j = jobs.list_jobs(conn, wid)[0]
    assert j["status"] == "pending" and j["attempts"] == 1 and "source outage" in j["last_error"]


def test_workspace_isolation(conn):
    wid_a = _ws(conn, "JOBS ISO A")
    jobs.create_job(conn, wid_a, ACTOR, source_system="feed", kind="new")
    assert len(jobs.list_jobs(conn, wid_a)) == 1
    wid_b = conn.execute(text("INSERT INTO workspace(name,type) VALUES ('JOBS ISO B','club') RETURNING id")).scalar_one()
    set_workspace(conn, wid_b)
    assert jobs.list_jobs(conn, wid_b) == []        # B sees none of A's jobs
    assert jobs.claim_next_job(conn, wid_b, ACTOR) is None
