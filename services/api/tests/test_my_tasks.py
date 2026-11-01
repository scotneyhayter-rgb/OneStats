"""Unified "My Tasks" aggregation (Part 16) — reuses the verification queue + Research Centre tasks.

Rolled back per test; skipped without a live DB; runs as ``onestats_app`` under FORCE RLS. Verifies
that tasks are filtered by the caller's effective permissions (a viewer sees none, a verifier sees
the approval queue, an editor sees drafts, a researcher sees research tasks) and that a self-
submitted scorecard is flagged for the approver.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import competitions, matches, my_tasks
from onestats.domain.research import tasks as research_tasks

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
SUBMITTER = "11111111-1111-1111-1111-111111111111"
APPROVER = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def conn():
    eng = create_engine(settings.database_url, future=True)
    with eng.connect() as c:
        trans = c.begin()
        try:
            yield c
        finally:
            trans.rollback()


def _ws(conn) -> uuid.UUID:
    wid = conn.execute(
        text("INSERT INTO workspace(name, short_name, type) VALUES ('T', :s, 'club') RETURNING id"),
        {"s": f"t-{uuid.uuid4().hex[:8]}"},
    ).scalar_one()
    set_workspace(conn, wid)
    return wid


def test_tasks_filtered_by_permission(conn):
    wid = _ws(conn)
    comp = competitions.create_competition(conn, wid, SUBMITTER, name="L")
    # one draft, one submitted-for-approval
    matches.create_match(conn, wid, SUBMITTER, competition_id=comp)
    mid = matches.create_match(conn, wid, SUBMITTER, competition_id=comp)
    matches.set_approval(conn, wid, SUBMITTER, mid, status="awaiting_approval")
    research_tasks.create_task(conn, wid, SUBMITTER, title="Find 1975/76 scorebook")

    viewer = my_tasks.my_tasks(conn, wid, {"match.view", "ask.query"}, APPROVER)
    assert viewer["total"] == 0

    editor = my_tasks.my_tasks(conn, wid, {"match.manage"}, SUBMITTER)
    assert editor["counts"]["draft"] == 1 and editor["counts"]["approval"] == 0

    verifier = my_tasks.my_tasks(conn, wid, {"scorecard.approve"}, APPROVER)
    assert verifier["counts"]["approval"] == 1
    assert verifier["tasks"][0]["self_submitted"] is False  # approver != submitter

    researcher = my_tasks.my_tasks(conn, wid, {"research.manage"}, APPROVER)
    assert researcher["counts"]["research"] == 1
    assert researcher["tasks"][0]["title"] == "Find 1975/76 scorebook"


def test_self_submitted_flagged_for_approver(conn):
    wid = _ws(conn)
    comp = competitions.create_competition(conn, wid, SUBMITTER, name="L")
    mid = matches.create_match(conn, wid, SUBMITTER, competition_id=comp)
    matches.set_approval(conn, wid, SUBMITTER, mid, status="awaiting_approval")
    # the SAME person views the approval queue -> self_submitted True (separation-of-duties signal)
    res = my_tasks.my_tasks(conn, wid, {"scorecard.approve"}, SUBMITTER)
    assert res["tasks"][0]["self_submitted"] is True
