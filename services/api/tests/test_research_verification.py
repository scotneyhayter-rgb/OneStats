"""Phase 10, Stage 10.11 — research verification reconciled with the Phase 7 approval machine.

verified_partial is a verified state whose present data is statistics-eligible (nothing invented);
disputed is held out of official statistics; the existing draft/awaiting/approved/rejected flow is
unchanged. Rolled back; skipped without a live DB.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import matches

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


def _match(conn, wid):
    return matches.create_match(conn, wid, ACTOR, status="draft")


def test_verified_partial_is_statistics_eligible(conn):
    wid = _ws(conn, "VER PARTIAL")
    mid = _match(conn, wid)
    m = matches.set_approval(conn, wid, ACTOR, mid, status="verified_partial", reason="result + batting only")
    assert m["approval_status"] == "verified_partial"
    assert m["approved_by"] is not None and m["approved_at"] is not None   # reviewer recorded
    assert matches.official_for_stats(m) is True                           # present data feeds stats


def test_disputed_is_held_out_of_statistics(conn):
    wid = _ws(conn, "VER DISPUTED")
    mid = _match(conn, wid)
    m = matches.set_approval(conn, wid, ACTOR, mid, status="disputed", reason="54 vs 45 unresolved")
    assert m["approval_status"] == "disputed"
    assert matches.official_for_stats(m) is False


def test_existing_approved_flow_unchanged(conn):
    wid = _ws(conn, "VER APPROVED")
    mid = _match(conn, wid)
    matches.set_approval(conn, wid, ACTOR, mid, status="awaiting_approval")
    m = matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    assert m["approval_status"] == "approved" and matches.official_for_stats(m) is True
    m2 = matches.set_approval(conn, wid, ACTOR, mid, status="rejected")
    assert m2["approval_status"] == "rejected" and matches.official_for_stats(m2) is False
