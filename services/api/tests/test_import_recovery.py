"""Phase 8, Stage 8.8 — import recovery (R2).

Interruption/recovery is tested during promotion as well as staging: a failure mid-promotion leaves
NO partially-committed data (the savepoint rolls back wholly), the staged batch survives for a retry,
and re-running promotion is idempotent — no duplicate or half-written matches. Rolled back per test;
skipped without a live DB.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import imports, matches
from onestats.domain.importing import pipeline
from onestats.domain.importing.adapters.csv_scorecard import CsvScorecardAdapter

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "11111111-1111-1111-1111-111111111111"

CSV = (
    "Date,HomeTeam,AwayTeam,Result\n"
    "2024-01-06,Alpha CC,Beta CC,Home win\n"
    "2024-01-13,Gamma CC,Delta CC,Away win\n"
)


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


def _dataset():
    a = CsvScorecardAdapter()
    return a.normalize(a.parse(CSV))


def test_failure_mid_promotion_leaves_nothing_then_retry_succeeds(conn, monkeypatch):
    wid = _ws(conn, "RECOVERY")
    # stage the batch (survives a failed promotion for retry)
    staged = pipeline.stage_dataset(conn, wid, ACTOR, _dataset())
    batch_id = staged["batch_id"]

    # simulate an interruption: fail on the SECOND match created during promotion
    real_create = matches.create_match
    calls = {"n": 0}

    def boom(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated interruption during promotion")
        return real_create(*args, **kwargs)

    monkeypatch.setattr(matches, "create_match", boom)

    sp = conn.begin_nested()
    with pytest.raises(RuntimeError, match="simulated interruption"):
        imports.promote_batch(conn, wid, ACTOR, batch_id)
    sp.rollback()   # the endpoint rolls the savepoint back on any failure

    # NOTHING was partially committed — no matches, no match_source, no teams from the aborted run
    assert conn.execute(text("SELECT count(*) FROM match")).scalar_one() == 0
    assert conn.execute(text("SELECT count(*) FROM match_source")).scalar_one() == 0
    # the batch is still staged and re-promotable
    assert imports.get_batch(conn, batch_id)["status"] not in ("promoted", "cancelled")

    # retry (interruption cleared) — promotion now completes with no duplicates
    monkeypatch.setattr(matches, "create_match", real_create)
    out = imports.promote_batch(conn, wid, ACTOR, batch_id)
    assert out["created"]["match"] == 2
    assert conn.execute(text("SELECT count(*) FROM match")).scalar_one() == 2


def test_retry_after_a_committed_import_is_idempotent(conn):
    """If an interruption happened AFTER a commit, a retry re-imports the same source with no
    duplicate matches/sources (idempotent on source refs)."""
    wid = _ws(conn, "RECOVERY IDEM")
    pipeline.import_dataset(conn, wid, ACTOR, dataset=_dataset(), commit=True)
    m1 = conn.execute(text("SELECT count(*) FROM match")).scalar_one()
    s1 = conn.execute(text("SELECT count(*) FROM match_source")).scalar_one()
    # the retry
    out = pipeline.import_dataset(conn, wid, ACTOR, dataset=_dataset(), commit=True)
    assert out["matched"]["match"] == 2
    assert conn.execute(text("SELECT count(*) FROM match")).scalar_one() == m1
    assert conn.execute(text("SELECT count(*) FROM match_source")).scalar_one() == s1
