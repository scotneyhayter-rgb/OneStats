"""Phase 9, Stages 9.4/9.10/9.11 — AutoSync orchestration.

Sync Now runs a real job via a fixture connector (queuing discoveries), historical discovery covers
each scope and resumes, startup reconciliation recovers interrupted jobs, and the dashboard reports
real DB counts. Rolled back; skipped without a live DB.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.autosync import jobs, service, sources
from onestats.domain.autosync.connectors import FixtureConnector, catalog

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "11111111-1111-1111-1111-111111111111"

ROWS = [
    {"Date": "2024-01-06", "HomeTeam": "Alpha CC", "AwayTeam": "Beta CC", "Result": "Home win"},
    {"Date": "2024-01-13", "HomeTeam": "Gamma CC", "AwayTeam": "Delta CC", "Result": "Away win"},
]
# a deterministic fixture connector registered in the catalog for the service to resolve
catalog.register(FixtureConnector("svc_feed", ROWS))


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


def _source(conn, wid):
    return sources.register_source(conn, wid, ACTOR, connector_id="svc_feed", name="svc_feed", enabled=True)


def test_sync_now_runs_a_real_job_and_queues_discoveries(conn):
    wid = _ws(conn, "SVC SYNC")
    _source(conn, wid)
    out = service.sync_now(conn, wid, ACTOR, source_system="svc_feed")
    assert out["ran"] is True and out["job"]["status"] == "succeeded"
    # dashboard reflects real counts
    dash = service.dashboard_summary(conn, wid)
    assert dash["sources"] == 1 and dash["pending_review"] == 2 and dash["new_matches"] == 2
    assert dash["coverage"].get("searched") == 1 and dash["last_success_at"] is not None


def test_sync_now_rejects_duplicate_active_job(conn):
    wid = _ws(conn, "SVC DUP")
    _source(conn, wid)
    jobs.create_job(conn, wid, ACTOR, source_system="svc_feed", kind="manual")   # an active job exists
    with pytest.raises(ValueError, match="duplicate_active_job"):
        service.sync_now(conn, wid, ACTOR, source_system="svc_feed")


def test_discover_history_covers_each_scope_and_is_resumable(conn):
    wid = _ws(conn, "SVC HIST")
    src = _source(conn, wid)
    connector = catalog.get("svc_feed")
    scopes = [{"key": "season:2022/23"}, {"key": "season:2023/24"}]
    out = service.discover_history(conn, wid, ACTOR, connector=connector, source_id=src["id"], scopes=scopes)
    assert out["searched"] == 2
    cov = {c["scope_key"] for c in __import__("onestats.domain.autosync.discovery", fromlist=["x"]).list_coverage(conn, wid)}
    assert {"season:2022/23", "season:2023/24"} <= cov
    # resume: a run that already did the first scope only searches the remaining one
    out2 = service.discover_history(conn, wid, ACTOR, connector=connector, source_id=src["id"],
                                    scopes=scopes, done={"season:2022/23"})
    assert out2["searched"] == 1


def test_sync_now_catches_up_an_interrupted_job(conn):
    wid = _ws(conn, "SVC CATCHUP")
    _source(conn, wid)
    # a job left 'interrupted' by a crash (offline) — should resume when AutoSync runs again
    jid = jobs.create_job(conn, wid, ACTOR, source_system="svc_feed", kind="historical")["id"]
    conn.execute(text("UPDATE sync_job SET status='interrupted', lease_owner=NULL, lease_expires_at=NULL WHERE id=:id"), {"id": jid})
    out = service.sync_now(conn, wid, ACTOR, source_system="svc_feed")   # runs the manual job + catch-up
    assert out["ran"] is True and out["caught_up"] >= 1
    assert jobs.get_job(conn, jid)["status"] in ("succeeded", "failed")   # the interrupted job resumed


def test_interface_only_source_marks_health_down_on_sync(conn):
    wid = _ws(conn, "SVC HEALTH")
    src = sources.register_source(conn, wid, ACTOR, connector_id="playhq", name="PlayHQ", enabled=True)
    service.sync_now(conn, wid, ACTOR, source_system="playhq")   # interface-only connector cannot fetch
    # a failed access is a HEALTH signal + failed coverage — never 'searched, no matches'
    assert sources.get_source(conn, src["id"])["reliability"] == "down"
    assert conn.execute(text("SELECT count(*) FROM discovery_coverage WHERE status='failed'")).scalar_one() >= 1


def test_startup_reconcile_recovers_interrupted_jobs(conn):
    wid = _ws(conn, "SVC RECON")
    _source(conn, wid)
    job = jobs.create_job(conn, wid, ACTOR, source_system="svc_feed", kind="new")
    jobs.claim_next_job(conn, wid, ACTOR)
    conn.execute(text("UPDATE sync_job SET lease_expires_at = now() - interval '1 minute' WHERE id = :id"), {"id": job["id"]})
    out = service.startup_reconcile(conn, wid, ACTOR)
    assert out["requeued"] == 1
    assert jobs.get_job(conn, job["id"])["status"] == "interrupted"
