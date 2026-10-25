"""Phase 10, Stages 10.14/10.15/10.16 — tasks/work queues, notes/evidence quality, assistance.

Rolled back; skipped without a live DB.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.research import assist, notes, projects, reconstruction, sources, tasks

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


def test_task_queue_lifecycle(conn):
    wid = _ws(conn, "TASKS")
    p = projects.create_project(conn, wid, ACTOR, title="RMCC 1890s")
    t = tasks.create_task(conn, wid, ACTOR, title="Find 1897 grand final scorecard", project_id=p["id"],
                          gap_kind="missing_scorecard", priority=5, assigned_to="scotney")
    assert t["status"] == "open" and t["priority"] == 5
    tasks.update_task(conn, wid, ACTOR, t["id"], status="in_progress")
    done = tasks.update_task(conn, wid, ACTOR, t["id"], status="resolved")
    assert done["status"] == "resolved" and done["resolved_at"] is not None
    assert len(tasks.list_tasks(conn, wid, project_id=p["id"])) == 1
    assert tasks.list_tasks(conn, wid, status="open") == []


def test_notes_evidence_classes(conn):
    wid = _ws(conn, "NOTES")
    notes.create_note(conn, wid, ACTOR, body="Club may have formed earlier than 1891", evidence_class="oral_history")
    notes.create_note(conn, wid, ACTOR, body="Result confirmed by two papers", evidence_class="supported")
    got = notes.list_notes(conn, wid)
    assert {n["evidence_class"] for n in got} == {"oral_history", "supported"}
    with pytest.raises(ValueError, match="invalid_evidence_class"):
        notes.create_note(conn, wid, ACTOR, body="x", evidence_class="rumour")
    with pytest.raises(ValueError, match="body_required"):
        notes.create_note(conn, wid, ACTOR, body="  ")


def test_suggestions_are_evidence_grounded(conn):
    wid = _ws(conn, "ASSIST")
    # a match dated 1931-11-02 with one linked source; a second source published 3 days later, unlinked
    s_linked = sources.create_source(conn, wid, ACTOR, title="Mon report", source_type="newspaper_article",
                                     publication="Argus", publication_date=dt.date(1931, 11, 2))["id"]
    m = reconstruction.start_reconstruction(conn, wid, ACTOR, match_date=dt.date(1931, 11, 2),
                                            date_precision="exact", source_id=s_linked)
    mid = m["id"]
    sources.create_source(conn, wid, ACTOR, title="Thu follow-up", source_type="newspaper_article",
                          publication="Argus", publication_date=dt.date(1931, 11, 5))
    out = assist.suggestions_for_match(conn, wid, mid)
    assert "match.result" in out["missing_key_fields"]            # no provenance yet
    titles = [r["title"] for r in out["suggested_related_sources"]]
    assert "Thu follow-up" in titles                               # near the match date, not yet linked
    assert out["disclaimer"].startswith("Suggestions are evidence-derived")
