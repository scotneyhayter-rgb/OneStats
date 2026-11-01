"""Match deletion (duplicate cleanup) — cascade + the verified-match permission tier.

Rolled back per test; skipped without a live DB. Deleting a match removes its whole scorecard
(cascade) and its statistics ledger rows; an approved match may only be deleted by someone who can
verify (scorecard.approve).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from onestats.api.v1.matches import _may_delete
from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import competitions, innings as inn, matches

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def conn():
    eng = create_engine(settings.database_url, future=True)
    with eng.connect() as c:
        t = c.begin()
        try:
            yield c
        finally:
            t.rollback()
    eng.dispose()


def _ws(conn):
    wid = conn.execute(text("INSERT INTO workspace(name, short_name, type) VALUES ('W',:s,'club') RETURNING id"),
                       {"s": f"w-{uuid.uuid4().hex[:8]}"}).scalar_one()
    set_workspace(conn, wid)
    return wid


def test_delete_removes_match_and_scorecard(conn):
    wid = _ws(conn)
    comp = competitions.create_competition(conn, wid, ACTOR, name="L")
    org = conn.execute(text("INSERT INTO organisation(workspace_id,name,kind) VALUES (:w,'Org','club') RETURNING id"), {"w": wid}).scalar_one()
    home = conn.execute(text("INSERT INTO team(workspace_id,organisation_id,name) VALUES (:w,:o,'H') RETURNING id"), {"w": wid, "o": org}).scalar_one()
    away = conn.execute(text("INSERT INTO team(workspace_id,organisation_id,name) VALUES (:w,:o,'A') RETURNING id"), {"w": wid, "o": org}).scalar_one()
    mid = matches.create_match(conn, wid, ACTOR, competition_id=comp)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    assert conn.execute(text("SELECT count(*) FROM innings WHERE match_id=:m"), {"m": mid}).scalar_one() == 1

    before = matches.delete_match(conn, wid, ACTOR, mid)
    assert before["id"]
    assert matches.get_match(conn, mid) is None
    # the scorecard children cascaded away
    assert conn.execute(text("SELECT count(*) FROM innings WHERE match_id=:m"), {"m": mid}).scalar_one() == 0
    assert conn.execute(text("SELECT count(*) FROM match_team WHERE match_id=:m"), {"m": mid}).scalar_one() == 0
    # audited
    n = conn.execute(text("SELECT count(*) FROM audit_log WHERE action='match.delete' AND entity_id=:m"),
                     {"m": str(mid)}).scalar_one()
    assert n == 1


def test_delete_unknown_raises(conn):
    _ws(conn)
    with pytest.raises(ValueError, match="match_not_found"):
        matches.delete_match(conn, uuid.uuid4(), ACTOR, uuid.uuid4())


def test_verified_match_delete_requires_verifier():
    # draft: deletable with match.manage alone
    assert _may_delete({"approval_status": "draft"}, {"match.manage"}) is True
    assert _may_delete({"approval_status": "rejected"}, {"match.manage"}) is True
    # approved/verified_partial: needs scorecard.approve
    assert _may_delete({"approval_status": "approved"}, {"match.manage"}) is False
    assert _may_delete({"approval_status": "approved"}, {"match.manage", "scorecard.approve"}) is True
    assert _may_delete({"approval_status": "verified_partial"}, {"match.manage"}) is False
