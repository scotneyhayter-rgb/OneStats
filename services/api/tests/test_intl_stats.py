"""Format-aware international statistics (Part H) — DB-backed, rolled back; skipped without a live DB.

Proves the per-format split is a genuine partition of the approved ledger: a player's Test and ODI
runs/wickets are reported separately and the ``all`` line is their honest union — never pooled wrongly,
never fabricated. Also checks single-format leaderboards isolate correctly and bad inputs are rejected.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import batting, bowling, competitions, matches, people, recalc
from onestats.domain import innings as inn
from onestats.domain.intl import stats as intl_stats

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
    wid = conn.execute(text("INSERT INTO workspace(name, type) VALUES (:n,'international') RETURNING id"),
                       {"n": name}).scalar_one()
    conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a, :u) ON CONFLICT (id) DO NOTHING"),
                 {"a": ACTOR, "u": f"actor-{name}"})
    set_workspace(conn, wid)
    return wid


def _team(conn, wid, name):
    org = conn.execute(text("INSERT INTO organisation(workspace_id,name,kind) VALUES (:w,:n,'intl_team') RETURNING id"),
                       {"w": wid, "n": name}).scalar_one()
    return conn.execute(text("INSERT INTO team(workspace_id,organisation_id,name) VALUES (:w,:o,:n) RETURNING id"),
                        {"w": wid, "o": org, "n": name}).scalar_one()


def _match(conn, wid, *, fmt, date, home, away, batter, bowler, runs, wkts, runs_conceded):
    """One approved single-innings match: `batter` (home) scores `runs`, `bowler` (away) takes `wkts`."""
    mid = matches.create_match(conn, wid, ACTOR, format=fmt, match_date=date)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True, captain_person_id=batter)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False, captain_person_id=bowler)
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=batter, batting_position=1,
                         runs=runs, balls_faced=runs, dismissal_type="not_out")
    bowling.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=bowler, legal_balls=60, maidens=0,
                         runs_conceded=runs_conceded, wickets=wkts)
    matches.set_result(conn, wid, ACTOR, mid, result_type="home_win", won_by_team_id=home)
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    recalc.recompute_match(conn, wid, ACTOR, mid)
    return mid


@pytest.fixture
def world(conn):
    wid = _ws(conn, "INTL STATS")
    home, away = _team(conn, wid, "Australia"), _team(conn, wid, "England")
    batter = people.create_person(conn, wid, ACTOR, display_name="Opener")
    bowler = people.create_person(conn, wid, ACTOR, display_name="Seamer")
    # a Test and an ODI for the SAME two players, with different figures in each
    _match(conn, wid, fmt="test", date=dt.date(2024, 1, 10), home=home, away=away,
           batter=batter, bowler=bowler, runs=100, wkts=4, runs_conceded=30)
    _match(conn, wid, fmt="odi", date=dt.date(2024, 2, 10), home=home, away=away,
           batter=batter, bowler=bowler, runs=50, wkts=2, runs_conceded=20)
    return {"wid": wid, "batter": str(batter), "bowler": str(bowler)}


def test_career_splits_by_format_and_sums_to_all(conn, world):
    career = intl_stats.format_career(conn, world["wid"], world["batter"])
    assert career["formats"]["test"]["batting"]["runs"] == 100
    assert career["formats"]["odi"]["batting"]["runs"] == 50
    assert career["formats"]["t20i"]["batting"]["runs"] == 0          # no T20I played -> genuine zero
    assert career["all"]["batting"]["runs"] == 150                    # honest union of the two formats
    # the format lines are distinct careers, not the pooled figure
    assert career["formats"]["test"]["batting"]["runs"] != career["all"]["batting"]["runs"]


def test_bowling_splits_by_format(conn, world):
    career = intl_stats.format_career(conn, world["wid"], world["bowler"])
    assert career["formats"]["test"]["bowling"]["wickets"] == 4
    assert career["formats"]["odi"]["bowling"]["wickets"] == 2
    assert career["all"]["bowling"]["wickets"] == 6


def test_leaders_are_scoped_to_one_format(conn, world):
    test_bat = intl_stats.format_leaders(conn, world["wid"], "test", "batting")
    row = next(r for r in test_bat if r["subject_id"] == world["batter"])
    assert row["runs"] == 100                                        # Test only, not 150
    odi_bowl = intl_stats.format_leaders(conn, world["wid"], "odi", "bowling")
    brow = next(r for r in odi_bowl if r["subject_id"] == world["bowler"])
    assert brow["wickets"] == 2


def test_empty_format_is_zero_not_fabricated(conn, world):
    # T20I has no matches: a leaderboard is empty, not a made-up ranking.
    assert intl_stats.format_leaders(conn, world["wid"], "t20i", "batting") == []


def test_bad_inputs_rejected(conn, world):
    with pytest.raises(ValueError):
        intl_stats.format_leaders(conn, world["wid"], "odi", "nonsense")
    with pytest.raises(ValueError):
        intl_stats.format_leaders(conn, world["wid"], "firstclass", "batting")
