"""Statistical-integrity regressions (2026-10-26):

1. Career bowling economy across DIFFERENT over lengths — computed from actual balls bowled and each
   match's own balls-per-over (six-ball, eight-ball, …), never one assumed over length across a career.
2. Multiple wicketkeepers in one innings — verified catches/stumpings attributed to the keeper who took
   them; an unknown keeper is not invented.

Independently hand-computed expected values. Requires a live DB; rolled back.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import batting, bowling, competitions, matches, people, playing_conditions
from onestats.domain import innings as inn
from onestats.domain.stats import engine, records_detail

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


def _season(conn, wid, comp, label, y):
    return conn.execute(text("INSERT INTO season(workspace_id,competition_id,label,start_date) "
                             "VALUES (:w,:c,:l,:d) RETURNING id"),
                        {"w": wid, "c": comp, "l": label, "d": dt.date(y, 10, 1)}).scalar_one()


def test_career_economy_across_mixed_over_lengths(conn):
    """A bowler whose career spans a six-ball-over competition and an eight-ball-over competition: career
    economy must use each match's real over length, not one assumed value."""
    wid = _ws(conn, "ECON MIX")
    comp6 = competitions.create_competition(conn, wid, ACTOR, name="Six-ball Comp")
    comp8 = competitions.create_competition(conn, wid, ACTOR, name="Eight-ball Comp")
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="competition", target_id=comp6, balls_per_over=6)
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="competition", target_id=comp8, balls_per_over=8)
    s6 = _season(conn, wid, comp6, "2010/11", 2010)
    s8 = _season(conn, wid, comp8, "1975/76", 1975)
    home, away = _team(conn, wid, "Home"), _team(conn, wid, "Away")
    bwl = people.create_person(conn, wid, ACTOR, display_name="Mixed-Era Bowler")
    bat = people.create_person(conn, wid, ACTOR, display_name="Batter")

    def _match(comp, season, balls, runs):
        mid = matches.create_match(conn, wid, ACTOR, competition_id=comp, season_id=season)
        matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
        matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
        i2 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=away, bowling_team_id=home)
        batting.create_entry(conn, wid, ACTOR, innings_id=i2, person_id=bat, batting_position=1, runs=5, dismissal_type="bowled")
        bowling.create_entry(conn, wid, ACTOR, innings_id=i2, person_id=bwl, legal_balls=balls, runs_conceded=runs, wickets=2)
        matches.set_approval(conn, wid, ACTOR, mid, status="approved")

    _match(comp6, s6, balls=60, runs=30)   # 6-ball: 60/6 = 10 overs, economy 3.00
    _match(comp8, s8, balls=64, runs=32)   # 8-ball: 64/8 =  8 overs, economy 4.00

    r = engine.person_bowling(conn, {"workspace_id": wid}, bwl)
    # career: true overs = 10 + 8 = 18; runs = 62; economy = 62 / 18 = 3.44 (NOT 3.00 or 4.00)
    assert r["overs"] == 18.0
    assert r["economy"] == 3.44
    assert r["economy_incomplete"] is False
    # a naive single-over-length assumption would give 62/(124/6)=3.00 or 62/(124/8)=4.00 — both wrong
    assert r["economy"] not in (3.0, 4.0)


def test_economy_flagged_when_over_length_unrecorded(conn):
    """A match with no recorded over length is excluded from the economy and the figure is flagged."""
    wid = _ws(conn, "ECON UNK")
    comp6 = competitions.create_competition(conn, wid, ACTOR, name="Six-ball")
    comp_unk = competitions.create_competition(conn, wid, ACTOR, name="Unknown over length")
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="competition", target_id=comp6, balls_per_over=6)
    s6 = _season(conn, wid, comp6, "2010/11", 2010)
    su = _season(conn, wid, comp_unk, "1900/01", 1900)
    home, away = _team(conn, wid, "H"), _team(conn, wid, "A")
    bwl = people.create_person(conn, wid, ACTOR, display_name="Bowler")
    bat = people.create_person(conn, wid, ACTOR, display_name="Bat")
    for comp, season, balls, runs in ((comp6, s6, 60, 30), (comp_unk, su, 48, 24)):
        mid = matches.create_match(conn, wid, ACTOR, competition_id=comp, season_id=season)
        matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
        matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
        i2 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=away, bowling_team_id=home)
        batting.create_entry(conn, wid, ACTOR, innings_id=i2, person_id=bat, batting_position=1, runs=5, dismissal_type="bowled")
        bowling.create_entry(conn, wid, ACTOR, innings_id=i2, person_id=bwl, legal_balls=balls, runs_conceded=runs, wickets=2)
        matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    r = engine.person_bowling(conn, {"workspace_id": wid}, bwl)
    # only the six-ball match contributes overs: 10 overs, 30 runs -> economy 3.00, flagged incomplete
    assert r["overs"] == 10.0 and r["economy"] == 3.0 and r["economy_incomplete"] is True


def test_multiple_wicketkeepers_in_one_innings(conn):
    """Two keepers in one innings: each is credited only with the dismissals they took; an unknown-keeper
    dismissal is not attributed."""
    wid = _ws(conn, "TWO KEEPERS")
    comp = competitions.create_competition(conn, wid, ACTOR, name="L")
    se = _season(conn, wid, comp, "2024/25", 2024)
    home, away = _team(conn, wid, "H"), _team(conn, wid, "A")
    k1 = people.create_person(conn, wid, ACTOR, display_name="Keeper One")
    k2 = people.create_person(conn, wid, ACTOR, display_name="Keeper Two")
    slip = people.create_person(conn, wid, ACTOR, display_name="Slip")
    hb = [people.create_person(conn, wid, ACTOR, display_name=f"HB{i}") for i in range(5)]
    mid = matches.create_match(conn, wid, ACTOR, competition_id=comp, season_id=se)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False,
                     wicketkeeper_person_id=k1, wicketkeeper2_person_id=k2)
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    # k1: one caught-behind. k2: one stumping + one catch (as second keeper). slip: one outfield catch.
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=hb[0], batting_position=1, runs=4,
                         dismissal_type="caught_behind", fielder_person_id=k1)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=hb[1], batting_position=2, runs=0,
                         dismissal_type="stumped", fielder_person_id=k2)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=hb[2], batting_position=3, runs=9,
                         dismissal_type="caught", fielder_person_id=k2)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=hb[3], batting_position=4, runs=12,
                         dismissal_type="caught", fielder_person_id=slip)
    # an unknown-keeper caught behind (no fielder recorded) -> must NOT be attributed to anyone
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=hb[4], batting_position=5, runs=1,
                         dismissal_type="caught_behind", fielder_person_id=None)
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")

    f = {"workspace_id": wid}
    # keeper leaderboard: k1 one keeper catch; k2 one keeper catch + one stumping
    k1s = engine.person_fielding(conn, f, k1)
    k2s = engine.person_fielding(conn, f, k2)
    assert k1s["keeper_catches"] == 1 and k1s["stumpings"] == 0 and k1s["keeper_dismissals"] == 1
    assert k2s["keeper_catches"] == 1 and k2s["stumpings"] == 1 and k2s["keeper_dismissals"] == 2
    # slip is an outfield catch, not a keeper dismissal
    assert engine.person_fielding(conn, f, slip)["keeper_catches"] == 0
    # WK-dismissals-in-an-innings attributes per keeper, not to a single primary keeper
    rows = records_detail.most_wk_dismissals_in_innings(conn, f)
    by = {r["player"]: r for r in rows}
    assert by["Keeper Two"]["total"] == 2 and by["Keeper Two"]["catches"] == 1 and by["Keeper Two"]["stumpings"] == 1
    assert by["Keeper One"]["total"] == 1
    # the unknown-keeper dismissal was not invented onto anyone
    assert sum(r["total"] for r in rows) == 3
