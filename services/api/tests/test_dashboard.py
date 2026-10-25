"""Workspace dashboard summary — real counts, empty state, recent activity, membership.

Rolled back; skipped without a live DB.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import dashboard, matches

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


def test_empty_workspace_is_all_zeros(conn):
    wid = _ws(conn, "DASH EMPTY")
    d = dashboard.workspace_dashboard(conn, wid)
    assert d["is_empty"] is True
    assert d["totals"]["matches"] == 0 and d["totals"]["players"] == 0
    assert d["attention"]["scorecards_awaiting_approval"] == 0
    assert d["recent_activity"] == []


def test_real_counts_and_attention(conn):
    wid = _ws(conn, "DASH DATA")
    conn.execute(text("INSERT INTO person(workspace_id, display_name) VALUES (:w, 'A Smith')"), {"w": wid})
    comp = conn.execute(text("INSERT INTO competition(workspace_id, name) VALUES (:w, 'ADCA') RETURNING id"),
                        {"w": wid}).scalar_one()
    conn.execute(text("INSERT INTO season(workspace_id, competition_id, label) VALUES (:w, :c, '1931/32')"),
                 {"w": wid, "c": comp})
    m_appr = matches.create_match(conn, wid, ACTOR)
    matches.set_approval(conn, wid, ACTOR, m_appr, status="approved")
    m_await = matches.create_match(conn, wid, ACTOR)
    matches.set_approval(conn, wid, ACTOR, m_await, status="awaiting_approval")
    m_disp = matches.create_match(conn, wid, ACTOR)
    matches.set_approval(conn, wid, ACTOR, m_disp, status="disputed")

    d = dashboard.workspace_dashboard(conn, wid)
    assert d["is_empty"] is False
    assert d["totals"]["matches"] == 3 and d["totals"]["players"] == 1
    assert d["totals"]["approved_scorecards"] == 1 and d["totals"]["seasons"] == 1
    assert d["attention"]["scorecards_awaiting_approval"] == 1
    assert d["attention"]["research_conflicts"] == 1          # the disputed match
    assert d["research"]["incomplete_scorecards"] == 0        # all three were transitioned out of draft
    assert len(d["recent_activity"]) > 0                      # audit-backed activity
    assert any(a["category"] == "Scorecard" for a in d["recent_activity"])
