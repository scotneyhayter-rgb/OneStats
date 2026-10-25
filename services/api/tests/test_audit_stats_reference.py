"""Comprehensive-audit reference tests: statistics verified against INDEPENDENTLY hand-computed
expected values (not by comparing two outputs of the same code).

One carefully-constructed match drives batting, bowling, fielding/keeping and captaincy through the
one engine. Expected values are worked out by hand in the comments. Requires a live DB; rolled back.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import batting, bowling, competitions, matches, people
from onestats.domain import innings as inn
from onestats.domain.stats import engine

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
                 {"a": ACTOR, "u": f"a-{name}"})
    set_workspace(conn, wid)
    return wid


def _team(conn, wid, name):
    org = conn.execute(text("INSERT INTO organisation(workspace_id,name,kind) VALUES (:w,:n,'club') RETURNING id"),
                       {"w": wid, "n": name + " CC"}).scalar_one()
    return conn.execute(text("INSERT INTO team(workspace_id,organisation_id,name) VALUES (:w,:o,:n) RETURNING id"),
                        {"w": wid, "o": org, "n": name}).scalar_one()


def test_batting_reference_values(conn):
    """Hand-computed batting: averages over dismissals, SR over known balls, 50s/100s/ducks, unknown≠duck."""
    wid = _ws(conn, "REF BAT")
    comp = competitions.create_competition(conn, wid, ACTOR, name="L")
    s = conn.execute(text("INSERT INTO season(workspace_id,competition_id,label,start_date) "
                          "VALUES (:w,:c,'2024/25',:d) RETURNING id"),
                     {"w": wid, "c": comp, "d": dt.date(2024, 10, 1)}).scalar_one()
    home, away = _team(conn, wid, "H"), _team(conn, wid, "A")
    # batters
    b50 = people.create_person(conn, wid, ACTOR, display_name="Fifty Maker")
    duck = people.create_person(conn, wid, ACTOR, display_name="Duck")
    ton = people.create_person(conn, wid, ACTOR, display_name="Centurion")
    unk = people.create_person(conn, wid, ACTOR, display_name="Unknown Runs")

    mid = matches.create_match(conn, wid, ACTOR, competition_id=comp, season_id=s)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=b50, batting_position=1,
                         runs=50, balls_faced=40, fours=6, sixes=1, dismissal_type="bowled")
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=duck, batting_position=2,
                         runs=0, balls_faced=3, dismissal_type="bowled")
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=ton, batting_position=3,
                         runs=120, balls_faced=100, dismissal_type="not_out")
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=unk, batting_position=4,
                         runs=None, balls_faced=None, dismissal_type="lbw")
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")

    f = {"workspace_id": wid}
    # Fifty Maker: 50 runs, out once -> avg 50.0; SR = 50*100/40 = 125.0; one fifty; HS 50
    r = engine.person_batting(conn, f, b50)
    assert r["runs"] == 50 and r["dismissed"] == 1 and r["average"] == 50.0
    assert r["strike_rate"] == 125.0 and r["fifties"] == 1 and r["hundreds"] == 0
    assert r["highest_score"] == 50 and r["ducks"] == 0 and r["fours"] == 6 and r["sixes"] == 1
    # Duck: 0 and out -> one duck, avg 0.0
    r = engine.person_batting(conn, f, duck)
    assert r["runs"] == 0 and r["ducks"] == 1 and r["dismissed"] == 1 and r["average"] == 0.0
    # Centurion: 120 not out -> avg None (never dismissed), SR 120.0, one hundred, HS 120
    r = engine.person_batting(conn, f, ton)
    assert r["runs"] == 120 and r["not_outs"] == 1 and r["dismissed"] == 0 and r["average"] is None
    assert r["strike_rate"] == 120.0 and r["hundreds"] == 1 and r["highest_score"] == 120 and r["ducks"] == 0
    # Unknown runs: NOT a duck, runs a known-minimum, SR not computed (no known balls)
    r = engine.person_batting(conn, f, unk)
    assert r["ducks"] == 0 and r["runs_known_minimum"] is True and r["strike_rate"] is None


def test_bowling_reference_with_eight_ball_overs(conn):
    """Hand-computed bowling incl. the historical 8-ball over (the case a hardcoded *6 gets wrong)."""
    wid = _ws(conn, "REF BOWL")
    comp = competitions.create_competition(conn, wid, ACTOR, name="L")
    s = conn.execute(text("INSERT INTO season(workspace_id,competition_id,label,start_date) "
                          "VALUES (:w,:c,'1975/76',:d) RETURNING id"),
                     {"w": wid, "c": comp, "d": dt.date(1975, 10, 1)}).scalar_one()
    home, away = _team(conn, wid, "H"), _team(conn, wid, "A")
    bwl = people.create_person(conn, wid, ACTOR, display_name="Demon Bowler")
    bat = people.create_person(conn, wid, ACTOR, display_name="Opposition Bat")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=comp, season_id=s)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    i2 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=away, bowling_team_id=home)
    batting.create_entry(conn, wid, ACTOR, innings_id=i2, person_id=bat, batting_position=1,
                         runs=10, dismissal_type="bowled")
    # 48 legal balls, 24 conceded, 5 wickets
    bowling.create_entry(conn, wid, ACTOR, innings_id=i2, person_id=bwl, legal_balls=48,
                         maidens=2, runs_conceded=24, wickets=5)
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")

    f = {"workspace_id": wid}
    # avg = 24/5 = 4.8; SR = 48/5 = 9.6; 5wi = 1; best match wickets = 5
    r8 = engine.person_bowling(conn, f, bwl, over_length=8)
    assert r8["wickets"] == 5 and r8["runs"] == 24 and r8["average"] == 4.8
    assert r8["strike_rate"] == 9.6 and r8["five_wkt_innings"] == 1 and r8["best_match_wickets"] == 5
    # 8-ball overs: 48/8 = 6 overs -> economy 24/6 = 4.0
    assert r8["economy"] == 4.0
    # 6-ball overs: 48/6 = 8 overs -> economy 24/8 = 3.0  (proves over length actually changes economy)
    r6 = engine.person_bowling(conn, f, bwl, over_length=6)
    assert r6["economy"] == 3.0


def test_fielding_keeper_classification_reference(conn):
    """Keeper catches / stumpings / run outs / field catches must be classified independently."""
    wid = _ws(conn, "REF FIELD")
    comp = competitions.create_competition(conn, wid, ACTOR, name="L")
    s = conn.execute(text("INSERT INTO season(workspace_id,competition_id,label,start_date) "
                          "VALUES (:w,:c,'2024/25',:d) RETURNING id"),
                     {"w": wid, "c": comp, "d": dt.date(2024, 10, 1)}).scalar_one()
    home, away = _team(conn, wid, "H"), _team(conn, wid, "A")
    keeper = people.create_person(conn, wid, ACTOR, display_name="Keeper")
    fielder = people.create_person(conn, wid, ACTOR, display_name="Slip")
    runner = people.create_person(conn, wid, ACTOR, display_name="Cover")
    # four home batters, all dismissed by away fielders/keeper
    hb = [people.create_person(conn, wid, ACTOR, display_name=f"HB{i}") for i in range(4)]
    mid = matches.create_match(conn, wid, ACTOR, competition_id=comp, season_id=s)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False, wicketkeeper_person_id=keeper)
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    # caught by keeper, caught_behind by keeper, stumped by keeper, caught by slip, run out by cover
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=hb[0], batting_position=1,
                         runs=10, dismissal_type="caught", fielder_person_id=keeper)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=hb[1], batting_position=2,
                         runs=5, dismissal_type="caught_behind", fielder_person_id=keeper)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=hb[2], batting_position=3,
                         runs=7, dismissal_type="stumped", fielder_person_id=keeper)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=hb[3], batting_position=4,
                         runs=3, dismissal_type="caught", fielder_person_id=fielder)
    i2 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=2, batting_team_id=away, bowling_team_id=home)
    rb = people.create_person(conn, wid, ACTOR, display_name="Run-out Victim")
    batting.create_entry(conn, wid, ACTOR, innings_id=i2, person_id=rb, batting_position=1,
                         runs=2, dismissal_type="run_out", fielder_person_id=runner)
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")

    f = {"workspace_id": wid}
    # keeper: 1 caught-as-keeper + 1 caught_behind = 2 keeper catches; 1 stumping;
    #         total catches include keeper catches (=2); keeper dismissals = 2 + 1 = 3; no field catch, no run out
    k = engine.person_fielding(conn, f, keeper)
    assert k["keeper_catches"] == 2 and k["stumpings"] == 1 and k["field_catches"] == 0
    assert k["catches"] == 2 and k["keeper_dismissals"] == 3 and k["run_outs"] == 0
    # slip: one field catch, not a keeper
    sl = engine.person_fielding(conn, f, fielder)
    assert sl["field_catches"] == 1 and sl["catches"] == 1 and sl["keeper_catches"] == 0
    # cover: one run out, never a catch or bowler wicket
    co = engine.person_fielding(conn, f, runner)
    assert co["run_outs"] == 1 and co["catches"] == 0


def test_captaincy_win_pct_reference(conn):
    """Win % is wins over eligible matches (no-results excluded) — hand-computed."""
    wid = _ws(conn, "REF CAPT")
    comp = competitions.create_competition(conn, wid, ACTOR, name="L")
    s = conn.execute(text("INSERT INTO season(workspace_id,competition_id,label,start_date) "
                          "VALUES (:w,:c,'2024/25',:d) RETURNING id"),
                     {"w": wid, "c": comp, "d": dt.date(2024, 10, 1)}).scalar_one()
    home, away = _team(conn, wid, "H"), _team(conn, wid, "A")
    cap = people.create_person(conn, wid, ACTOR, display_name="Skipper")
    # 4 matches captained: 2 wins, 1 loss, 1 no_result -> eligible = 3, win% = 2/3 = 66.7
    outcomes = [("home_win", home), ("home_win", home), ("away_win", away), ("no_result", None)]
    for n, (rt, won) in enumerate(outcomes):
        mid = matches.create_match(conn, wid, ACTOR, competition_id=comp, season_id=s)
        matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True, captain_person_id=cap)
        matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
        matches.set_result(conn, wid, ACTOR, mid, result_type=rt, won_by_team_id=won)
        matches.set_approval(conn, wid, ACTOR, mid, status="approved")

    rows = engine.captaincy_leaders(conn, {"workspace_id": wid}, min_eligible=0)
    me = next(r for r in rows if r["subject_id"] == str(cap))
    assert me["captained"] == 4 and me["wins"] == 2 and me["losses"] == 1 and me["no_results"] == 1
    assert me["eligible"] == 3 and me["win_pct"] == 66.7
