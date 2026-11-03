"""Cricsheet worker tick — downloads a bundle (offline MockTransport) and imports a batch end to end.

This drives the real :func:`cricsheet_worker.run_due`, which manages its own (committing) transactions,
so the test creates a throwaway workspace, scopes the run to it (``only_workspace``), and deletes it in a
``finally``. No network: the fetcher is injected with an httpx MockTransport. Verifies the download sits
OUTSIDE the DB transaction path by exercising the whole tick.
"""
from __future__ import annotations

import io
import json
import zipfile
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.intl import cricsheet_backfill as backfill
from onestats.domain.intl import cricsheet_download as dl
from onestats.domain.intl import cricsheet_worker

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "11111111-1111-1111-1111-111111111111"


def _bundle(n):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i in range(n):
            zf.writestr(f"{9000+i}.json", json.dumps({
                "info": {"match_type": "ODI", "gender": "male", "balls_per_over": 6, "dates": ["2024-03-01"],
                         "teams": [f"A{i}", f"B{i}"], "outcome": {"winner": f"A{i}", "by": {"runs": 3}},
                         "players": {f"A{i}": ["P1"], f"B{i}": ["P2"]}, "registry": {"people": {"P1": f"r{i}"}}},
                "innings": [{"team": f"A{i}", "overs": [{"over": 0, "deliveries": [
                    {"batter": "P1", "bowler": "P2", "runs": {"batter": 1, "extras": 0, "total": 1}}]}]}]}))
    return buf.getvalue()


def _factory():
    import httpx
    zb = _bundle(3)
    return dl.make_fetcher(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=zb, headers={"content-type": "application/zip"})),
        resolver=lambda h: ["93.184.216.34"], respect_robots=False)


def test_worker_tick_downloads_and_imports_then_cleans_up():
    app = create_engine(settings.database_url, future=True)
    su = create_engine(settings.migration_url, future=True)
    wid = None
    try:
        with app.connect() as c:
            t = c.begin()
            wid = c.execute(text("INSERT INTO workspace(name, type) VALUES (:n,'international') RETURNING id"),
                            {"n": f"CS WORKER {uuid4().hex[:8]}"}).scalar_one()
            c.execute(text("INSERT INTO app_user(id, username) VALUES (:a, :u) ON CONFLICT (id) DO NOTHING"),
                      {"a": ACTOR, "u": f"w-{uuid4().hex[:6]}"})
            set_workspace(c, wid)
            backfill.start(c, wid, ACTOR, "odi")
            t.commit()

        out = cricsheet_worker.run_due(app, fetcher_factory=_factory, only_workspace=wid, batch_size=10)
        assert out["ticked"] == 1
        assert out["runs"][0]["status"] == "completed" and out["runs"][0]["processed"] == 3

        with app.connect() as c:
            set_workspace(c, wid)
            n = c.execute(text("SELECT count(*) FROM match WHERE workspace_id=:w AND source_system='cricsheet'"),
                          {"w": wid}).scalar_one()
            state = backfill.get(c, wid, "odi")
        assert n == 3 and state["status"] == "completed" and state["imported"] == 3
    finally:
        if wid is not None:
            with su.connect() as c:
                t = c.begin()
                set_workspace(c, wid)
                c.execute(text("DELETE FROM audit_log WHERE workspace_id = :w"), {"w": wid})
                c.execute(text("DELETE FROM workspace WHERE id = :w"), {"w": wid})
                t.commit()
        app.dispose()
        su.dispose()
