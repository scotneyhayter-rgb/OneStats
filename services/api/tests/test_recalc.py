"""Automatic recalculation framework — official statistics ledger (Phase 7, Stage 7.8).

Rolled back per test; skipped without a live DB; runs as ``onestats_app`` under FORCE RLS. Covers
approved-only contribution, idempotency (no double counting), preservation of the last approved
version across edits, recompute on re-approval, removal on un-approval and on match deletion,
merge-aware aggregation, backfill, and workspace isolation.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import batting, bowling, competitions, matches, person_resolution, recalc
from onestats.domain import innings as inn
from onestats.domain import people

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


def _team(conn, wid, name):
    org = conn.execute(text("INSERT INTO organisation(workspace_id,name,kind) VALUES (:w,:n,'club') RETURNING id"),
                       {"w": wid, "n": name + " CC"}).scalar_one()
    return conn.execute(text("INSERT INTO team(workspace_id,organisation_id,name) VALUES (:w,:o,:n) RETURNING id"),
                        {"w": wid, "o": org, "n": name}).scalar_one()


def _scorecard(conn, wid):
    cid = competitions.create_competition(conn, wid, ACTOR, name="League")
    home, away = _team(conn, wid, "Home"), _team(conn, wid, "Away")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=cid)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    p1 = people.create_person(conn, wid, ACTOR, display_name="Batter A")
    p2 = people.create_person(conn, wid, ACTOR, display_name="Batter B")
    p3 = people.create_person(conn, wid, ACTOR, display_name="Bowler C")
    be1 = batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=p1, batting_position=1,
                               runs=50, balls_faced=40, fours=5, sixes=1, dismissal_type="not_out")
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=p2, batting_position=2,
                         runs=30, balls_faced=25, dismissal_type="bowled")
    bowling.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=p3, legal_balls=24, maidens=1,
                         runs_conceded=20, wickets=2)
    return mid, p1, p2, p3, be1


def test_only_approved_contributes_and_is_idempotent(conn):
    wid = _ws(conn, "RC OFFICIAL")
    mid, p1, _p2, p3, _ = _scorecard(conn, wid)
    # draft -> no official contributions
    recalc.recompute_match(conn, wid, ACTOR, mid)
    assert conn.execute(text("SELECT count(*) FROM match_stat_contribution")).scalar_one() == 0
    # approve -> contributions written (approval triggers recompute)
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    n = conn.execute(text("SELECT count(*) FROM match_stat_contribution")).scalar_one()
    assert n == 3   # p1, p2 batting + p3 bowling
    # idempotent: recompute again does not duplicate
    recalc.recompute_match(conn, wid, ACTOR, mid)
    assert conn.execute(text("SELECT count(*) FROM match_stat_contribution")).scalar_one() == 3
    bat = recalc.official_player_batting(conn, wid, p1)
    assert bat["runs"] == 50 and bat["innings"] == 1 and bat["not_out"] == 1 and bat["dismissed"] == 0
    assert bat["average"] is None   # never dismissed
    bowl = recalc.official_player_bowling(conn, wid, p3)
    assert bowl["wickets"] == 2 and bowl["runs"] == 20 and bowl["average"] == 10.0


def test_edit_after_approval_preserves_last_approved_until_reapproval(conn):
    wid = _ws(conn, "RC PRESERVE")
    mid, p1, _p2, _p3, be1 = _scorecard(conn, wid)
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    assert recalc.official_player_batting(conn, wid, p1)["runs"] == 50
    batting.update_entry(conn, wid, ACTOR, be1, runs=99)        # edit after approval
    matches.mark_revised_if_approved(conn, mid)
    assert recalc.official_player_batting(conn, wid, p1)["runs"] == 50   # ledger unchanged (last approved)
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")       # re-approve
    assert recalc.official_player_batting(conn, wid, p1)["runs"] == 99   # now updated, not doubled
    assert conn.execute(text("SELECT count(*) FROM match_stat_contribution")).scalar_one() == 3


def test_unapproving_and_deleting_removes_contributions(conn):
    wid = _ws(conn, "RC REMOVE")
    mid, p1, _p2, _p3, _ = _scorecard(conn, wid)
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    assert recalc.official_player_batting(conn, wid, p1)["runs"] == 50
    matches.set_approval(conn, wid, ACTOR, mid, status="rejected")        # un-approve
    assert recalc.official_player_batting(conn, wid, p1)["runs"] == 0
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    conn.execute(text("DELETE FROM match WHERE id = :m"), {"m": mid})     # duplicate removal
    assert conn.execute(text("SELECT count(*) FROM match_stat_contribution")).scalar_one() == 0


def test_merge_aware_aggregation(conn):
    """After merging two identities, official totals for the canonical person combine both."""
    wid = _ws(conn, "RC MERGE")
    mid, p1, p2, _p3, _ = _scorecard(conn, wid)
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    assert recalc.official_player_batting(conn, wid, p1)["runs"] == 50
    person_resolution.merge_people(conn, wid, ACTOR, canonical_id=p1, merged_id=p2, reason="same player")
    assert recalc.official_player_batting(conn, wid, p1)["runs"] == 80   # 50 + 30, no re-import needed


def test_backfill_recomputes_all_and_excludes_unapproved(conn):
    wid = _ws(conn, "RC BACKFILL")
    mid, _p1, _p2, _p3, _ = _scorecard(conn, wid)
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    # a second, unapproved match contributes nothing
    _scorecard(conn, wid)
    out = recalc.backfill(conn, wid, ACTOR)
    assert out["matches"] == 2 and out["contributions"] == 3   # only the approved match's 3 rows


def test_isolation(conn):
    wid_a = conn.execute(text("INSERT INTO workspace(name,type) VALUES ('RC ISO A','club') RETURNING id")).scalar_one()
    conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a,'rc-iso') ON CONFLICT (id) DO NOTHING"), {"a": ACTOR})
    set_workspace(conn, wid_a)
    mid, _p1, _p2, _p3, _ = _scorecard(conn, wid_a)
    matches.set_approval(conn, wid_a, ACTOR, mid, status="approved")
    assert conn.execute(text("SELECT count(*) FROM match_stat_contribution")).scalar_one() == 3
    wid_b = conn.execute(text("INSERT INTO workspace(name,type) VALUES ('RC ISO B','club') RETURNING id")).scalar_one()
    set_workspace(conn, wid_b)
    assert conn.execute(text("SELECT count(*) FROM match_stat_contribution")).scalar_one() == 0  # B sees none of A's
