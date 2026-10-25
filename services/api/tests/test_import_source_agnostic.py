"""Phase 8, Stage 8.3 — promotion is source-agnostic.

The shared promoter resolves identities against the batch's OWN ``source_system`` (not a hardcoded
CricketStatz), so any adapter's staged records promote correctly and a re-import is idempotent. Rolled
back per test; skipped without a live DB. Proves the threading without disturbing the CricketStatz path.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import imports, matches

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "11111111-1111-1111-1111-111111111111"
SRC = "news_archive"   # a non-CricketStatz source


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


def _stage_minimal_batch(conn, wid):
    """A tiny non-CS batch (club + two teams + one match) staged directly, as a generic adapter would."""
    batch_id = conn.execute(
        text("INSERT INTO import_batch(workspace_id, source_system, source_filename, created_by) "
             "VALUES (:w, :ss, 'archive.csv', :a) RETURNING id"),
        {"w": wid, "ss": SRC, "a": ACTOR},
    ).scalar_one()
    imports._insert_record(conn, wid, batch_id, "club", "C1", {"src": "C1"},
                           {"name": "Alpha CC", "kind": "club"}, resolution="new")
    for ref, name in (("T1", "Alpha 1st"), ("T2", "Beta 1st")):
        imports._insert_record(conn, wid, batch_id, "team", ref, {"src": ref},
                               {"name": name, "club_source_ref": "C1"}, resolution="new")
    imports._insert_record(conn, wid, batch_id, "match", "M1", {"src": "M1"}, {
        "home_team_source_ref": "T1", "away_team_source_ref": "T2",
        "date_played": "2024-02-01", "round": "1", "matchtype_label": "1 innings per side",
        "result": None, "result_status": "unknown",
    }, resolution="new")
    return batch_id


def test_non_cricketstatz_batch_promotes_under_its_own_source_system(conn):
    wid = _ws(conn, "SRC AGNOSTIC")
    batch_id = _stage_minimal_batch(conn, wid)
    out = imports.promote_batch(conn, wid, ACTOR, batch_id)
    assert out["created"]["team"] == 2 and out["created"]["match"] == 1 and out["created"]["club"] == 1

    # the canonical rows carry THIS source, not cricket_statz
    mid = conn.execute(text("SELECT id FROM match WHERE source_system = :ss AND source_ref = 'M1'"),
                       {"ss": SRC}).scalar_one()
    assert conn.execute(text("SELECT count(*) FROM team_source_identity WHERE source_system = :ss"),
                        {"ss": SRC}).scalar_one() == 2
    # and the sides resolved against the news_archive teams
    m = matches.get_match(conn, mid)
    assert m["match_date"].isoformat() == "2024-02-01"
    sides = conn.execute(text("SELECT count(*) FROM match_team WHERE match_id = :m"), {"m": mid}).scalar_one()
    assert sides == 2

    # a CricketStatz entity with the SAME source_ref is independent (no cross-source collision)
    assert conn.execute(text("SELECT count(*) FROM team WHERE source_system = 'cricket_statz' AND source_ref = 'T1'")).scalar_one() == 0


def test_reimport_same_source_is_idempotent(conn):
    wid = _ws(conn, "SRC IDEMPOTENT")
    imports.promote_batch(conn, wid, ACTOR, _stage_minimal_batch(conn, wid))
    teams_before = conn.execute(text("SELECT count(*) FROM team")).scalar_one()
    matches_before = conn.execute(text("SELECT count(*) FROM match")).scalar_one()
    # a second batch with the same source refs → everything matches, nothing duplicated
    out = imports.promote_batch(conn, wid, ACTOR, _stage_minimal_batch(conn, wid))
    assert out["matched"]["team"] == 2 and out["matched"]["match"] == 1 and out["matched"]["club"] == 1
    assert conn.execute(text("SELECT count(*) FROM team")).scalar_one() == teams_before
    assert conn.execute(text("SELECT count(*) FROM match")).scalar_one() == matches_before
