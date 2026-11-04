"""Live-source acceptance smoke test for the Internet Research Engine.

OPT-IN only: skipped unless ``ONESTATS_LIVE_RESEARCH_TEST=1`` (and a DB is configured), so normal CI
never touches the network. When enabled it runs a REAL investigation end to end against free public
sources (Wikipedia OpenSearch discovery → real page retrieval through the SSRF-hardened fetcher →
cricket-aware extraction → persisted findings), proving the pipeline works against genuine live data
without any paid API or key.

Run it manually:
    ONESTATS_LIVE_RESEARCH_TEST=1 .venv/Scripts/python -m pytest tests/test_research_live.py -s
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.research import engine as reng
from onestats.domain.research import jobs

settings = get_settings()
_enabled = os.environ.get("ONESTATS_LIVE_RESEARCH_TEST") == "1" and settings.db_configured
pytestmark = pytest.mark.skipif(not _enabled, reason="set ONESTATS_LIVE_RESEARCH_TEST=1 (and a DB) to run live")
ACTOR = "33333333-3333-3333-3333-333333333333"


def test_live_internet_research_end_to_end():
    eng = create_engine(settings.database_url, future=True)
    with eng.connect() as conn:
        trans = conn.begin()
        try:
            wid = conn.execute(text("INSERT INTO workspace(name, type) VALUES ('LIVE','club') RETURNING id")).scalar_one()
            conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a,'live') ON CONFLICT (id) DO NOTHING"),
                         {"a": ACTOR})
            set_workspace(conn, wid)

            jobs.create_job(conn, wid, ACTOR, query="Donald Bradman", depth="quick",
                                  context={"player": "Donald Bradman"})
            claimed = jobs.claim_next_job(conn, wid, ACTOR)
            assert claimed is not None

            done, guard = False, 0
            while not done and guard < 20:
                guard += 1
                res = reng.run_step(conn, wid, ACTOR, jobs.get_job(conn, claimed["id"]), settings=settings)
                done = res["done"]

            fetches = conn.execute(text("SELECT outcome, count(*) FROM research_fetch WHERE job_id=:j GROUP BY outcome"),
                                   {"j": claimed["id"]}).all()
            findings = jobs.list_findings(conn, wid)
            print("\nLIVE fetch outcomes:", dict(fetches))
            print("LIVE findings:", [(f["kind"], f["confidence"], f["url"]) for f in findings])

            # The run must have actually examined live sources and completed.
            assert any(o == "fetched" for o, _ in fetches), "no live page was successfully fetched"
            assert done is True
            # Findings (if any) must obey the honesty rules: never auto-approved, confidence capped.
            for f in findings:
                assert f["status"] == "pending_review"
                assert f["classification"] in ("new", "possible_duplicate", "additional_evidence", "insufficient", "unknown")
                assert f["confidence"] is None or 0.0 < f["confidence"] <= 0.9
        finally:
            trans.rollback()
    eng.dispose()
