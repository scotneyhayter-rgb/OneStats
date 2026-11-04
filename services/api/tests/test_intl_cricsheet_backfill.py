"""Resumable Cricsheet backfill — batches, resume-after-restart, pause/cancel. DB-backed, rolled back.

Proves: a backfill walks the bundle in bounded batches and completes; progress is resumable (a fresh
call processes only the not-yet-done matches, as it would after a restart); pause and cancel stop work;
and counts are genuine.
"""
from __future__ import annotations

import io
import json
import zipfile

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.intl import cricsheet_backfill as bf

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


def _doc(a, b):
    return {"info": {"match_type": "ODI", "gender": "male", "balls_per_over": 6, "dates": ["2024-02-01"],
                     "teams": [a, b], "outcome": {"winner": a, "by": {"runs": 5}},
                     "players": {a: ["P One"], b: ["P Two"]}, "registry": {"people": {"P One": "r1"}}},
            "innings": [{"team": a, "overs": [{"over": 0, "deliveries": [
                {"batter": "P One", "bowler": "P Two", "runs": {"batter": 1, "extras": 0, "total": 1}}]}]}]}


def _bundle(n):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i in range(n):
            zf.writestr(f"{1000+i}.json", json.dumps(_doc(f"Team{i}", f"Opp{i}")))
    return buf.getvalue()


def _ws(conn):
    wid = conn.execute(text("INSERT INTO workspace(name, type) VALUES ('CS BF','international') RETURNING id")).scalar_one()
    conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a,'bf') ON CONFLICT (id) DO NOTHING"), {"a": ACTOR})
    set_workspace(conn, wid)
    return wid


def test_backfill_processes_in_batches_and_completes(conn):
    wid = _ws(conn)
    bundle = _bundle(5)
    bf.start(conn, wid, ACTOR, "odi")
    r1 = bf.run_batch(conn, wid, ACTOR, "odi", bundle, batch_size=2)
    assert r1["processed"] == 2 and r1["status"] == "running" and r1["remaining"] == 3
    r2 = bf.run_batch(conn, wid, ACTOR, "odi", bundle, batch_size=2)   # resumes: next 2, not the first 2
    assert r2["processed"] == 2 and r2["remaining"] == 1
    r3 = bf.run_batch(conn, wid, ACTOR, "odi", bundle, batch_size=2)
    assert r3["processed"] == 1 and r3["status"] == "completed"
    state = bf.get(conn, wid, "odi")
    assert state["status"] == "completed" and state["processed"] == 5 and state["imported"] == 5
    # exactly five matches imported, none duplicated
    assert conn.execute(text("SELECT count(*) FROM match WHERE workspace_id=:w"), {"w": wid}).scalar_one() == 5
    # a further batch does nothing (already complete)
    assert bf.run_batch(conn, wid, ACTOR, "odi", bundle, batch_size=2)["ran"] is False


def test_pause_and_cancel_stop_work(conn):
    wid = _ws(conn)
    bundle = _bundle(4)
    bf.start(conn, wid, ACTOR, "odi")
    bf.run_batch(conn, wid, ACTOR, "odi", bundle, batch_size=1)        # 1 done
    bf.set_status(conn, wid, ACTOR, "odi", "pause")
    assert bf.run_batch(conn, wid, ACTOR, "odi", bundle, batch_size=1)["ran"] is False
    assert conn.execute(text("SELECT count(*) FROM match WHERE workspace_id=:w"), {"w": wid}).scalar_one() == 1
    # resume continues from where it was
    bf.set_status(conn, wid, ACTOR, "odi", "resume")
    assert bf.run_batch(conn, wid, ACTOR, "odi", bundle, batch_size=10)["processed"] == 3
    # cancel halts a fresh backfill
    bf.set_status(conn, wid, ACTOR, "odi", "cancel")
    assert bf.get(conn, wid, "odi")["status"] == "cancelled"
