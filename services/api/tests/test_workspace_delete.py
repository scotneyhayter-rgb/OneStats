"""Workspace deletion — Super-Admin, name-confirmed, cascading, audited.

Rolled back per test; skipped without a live DB. Verifies the exact short-name confirmation guard,
that deletion removes the workspace and its cascaded children (and its audit_log rows, which have a
RESTRICT FK), and that the removal is recorded in the global admin_audit log.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import audit, competitions, matches, workspaces

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


def _ws(conn, short):
    wid = conn.execute(
        text("INSERT INTO workspace(name, short_name, type) VALUES (:n,:s,'club') RETURNING id"),
        {"n": short.upper(), "s": short},
    ).scalar_one()
    set_workspace(conn, wid)
    return wid


def test_delete_requires_exact_short_name(conn):
    wid = _ws(conn, f"del-{uuid.uuid4().hex[:6]}")
    with pytest.raises(ValueError, match="confirmation_mismatch"):
        workspaces.delete_workspace(conn, wid, ACTOR, "not-the-name")
    assert workspaces.get_workspace(conn, wid) is not None  # still there


def test_delete_unknown_workspace_raises(conn):
    with pytest.raises(ValueError, match="workspace_not_found"):
        workspaces.delete_workspace(conn, uuid.uuid4(), ACTOR, "whatever")


def test_delete_removes_workspace_children_and_audits(conn):
    short = f"del-{uuid.uuid4().hex[:6]}"
    wid = _ws(conn, short)
    comp = competitions.create_competition(conn, wid, ACTOR, name="L")
    matches.create_match(conn, wid, ACTOR, competition_id=comp)
    audit.write_audit(conn, wid, ACTOR, "workspace.update", entity="workspace", entity_id=str(wid))
    assert conn.execute(text("SELECT count(*) FROM match")).scalar_one() == 1

    res = workspaces.delete_workspace(conn, wid, ACTOR, short.upper())  # confirmation is case-insensitive
    assert res["deleted"] is True and res["short_name"] == short

    # the workspace is gone, and its children cascaded (match removed), audit rows cleared
    assert workspaces.get_workspace(conn, wid) is None
    set_workspace(conn, wid)
    assert conn.execute(text("SELECT count(*) FROM match")).scalar_one() == 0
    assert conn.execute(text("SELECT count(*) FROM competition")).scalar_one() == 0
    # recorded in the global platform log
    n = conn.execute(
        text("SELECT count(*) FROM admin_audit WHERE action = :a"),
        {"a": f"workspace.delete:{short}:{wid}"},
    ).scalar_one()
    assert n == 1
