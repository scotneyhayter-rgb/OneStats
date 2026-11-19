"""Scoped player rankings — the weighted-index engine (Batting / Bowling / Allrounder).

Covers the two properties the methodology hinges on: index points are ABSOLUTE (the volume term is a
per-match rate, so the same per-match form scores the same regardless of how many matches are in the
window), and qualification scales/guards correctly. Rolled back; skipped without a live DB.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import batting, bowling, competitions, matches, people
from onestats.domain import innings as inn
from onestats.domain.stats import rankings
from onestats.reports import catalogue

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


def _p(conn, wid, name):
    return people.create_person(conn, wid, ACTOR, display_name=name)


def _match(conn, wid, comp, home, away, *, bats=(), bowls=(), away_bats=(), home_bowls=()):
    """A match: ``bats``/``bowls`` are the home innings (home bats, away bowls); ``away_bats``/``home_bowls``
    add a second innings (away bats, home bowls) so a player can both bat and bowl. Entries are
    (person, runs, balls) for batting and (person, legal_balls, runs_conceded, wickets) for bowling."""
    mid = matches.create_match(conn, wid, ACTOR, competition_id=comp)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    for pos, (pid, runs, balls) in enumerate(bats, 1):
        batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=pid, batting_position=pos,
                             runs=runs, balls_faced=balls, dismissal_type="bowled")
    for (pid, lb, rc, wk) in bowls:
        bowling.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=pid, legal_balls=lb, runs_conceded=rc, wickets=wk)
    if away_bats or home_bowls:
        i2 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=2, batting_team_id=away, bowling_team_id=home)
        for pos, (pid, runs, balls) in enumerate(away_bats, 1):
            batting.create_entry(conn, wid, ACTOR, innings_id=i2, person_id=pid, batting_position=pos,
                                 runs=runs, balls_faced=balls, dismissal_type="bowled")
        for (pid, lb, rc, wk) in home_bowls:
            bowling.create_entry(conn, wid, ACTOR, innings_id=i2, person_id=pid, legal_balls=lb, runs_conceded=rc, wickets=wk)
    matches.set_result(conn, wid, ACTOR, mid, result_type="home_win", won_by_team_id=home)
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    return mid


def _board(conn, wid, report):
    return {r["player"]: r for r in catalogue.report_rows(conn, wid, report, {"workspace_id": wid})["rows"]}


def test_index_points_are_a_per_match_rate_and_absolute(conn):
    """Two batters with identical per-match form but different match counts get the SAME index — proving
    the volume term is a per-match rate, so points are comparable across windows of different length."""
    wid = _ws(conn, "RANK ABS")
    comp = competitions.create_competition(conn, wid, ACTOR, name="League")
    home, away = _team(conn, wid, "Home"), _team(conn, wid, "Away")
    alice, bob = _p(conn, wid, "Alice"), _p(conn, wid, "Bob")
    # matches 1-2: both bat 50 off 50; matches 3-4: only Bob bats 50 off 50. Same avg/SR/RPM/milestone.
    _match(conn, wid, comp, home, away, bats=[(alice, 50, 50), (bob, 50, 50)])
    _match(conn, wid, comp, home, away, bats=[(alice, 50, 50), (bob, 50, 50)])
    _match(conn, wid, comp, home, away, bats=[(bob, 50, 50)])
    _match(conn, wid, comp, home, away, bats=[(bob, 50, 50)])

    bat = _board(conn, wid, "rank_batting")
    assert bat["Alice"]["innings"] == 2 and bat["Bob"]["innings"] == 4
    assert bat["Alice"]["points"] == bat["Bob"]["points"]          # per-match rate ⇒ identical, absolute
    assert bat["Alice"]["status"] == "" and bat["Bob"]["status"] == ""   # both qualified, both ranked


def test_bowling_qualification_min_overs(conn):
    """A bowler under the 20-over floor is shown as unranked (not hidden); one over it is ranked."""
    wid = _ws(conn, "RANK QUAL")
    comp = competitions.create_competition(conn, wid, ACTOR, name="League")
    home, away = _team(conn, wid, "Home"), _team(conn, wid, "Away")
    long_bowler, short_bowler = _p(conn, wid, "Longspell"), _p(conn, wid, "Shortspell")
    opener = _p(conn, wid, "Opener")
    # one match: Longspell bowls 150 balls (25 overs), Shortspell 60 balls (10 overs)
    _match(conn, wid, comp, home, away, bats=[(opener, 40, 50)],
           bowls=[(long_bowler, 150, 60, 5), (short_bowler, 60, 40, 1)])

    bowl = _board(conn, wid, "rank_bowling")
    assert bowl["Longspell"]["status"] == "" and bowl["Longspell"]["rank"] is not None
    assert bowl["Shortspell"]["status"] == rankings.UNRANKED and bowl["Shortspell"]["rank"] is None


def test_allrounder_is_product_and_zero_wickets_guarded(conn):
    """Allrounder index = batting × bowling ÷ 100 (from the two boards). A 0-wicket bowler still gets a
    finite index (the undefined average/strike-rate terms are guarded to 0)."""
    wid = _ws(conn, "RANK AR")
    comp = competitions.create_competition(conn, wid, ACTOR, name="League")
    home, away = _team(conn, wid, "Home"), _team(conn, wid, "Away")
    allie, donkey = _p(conn, wid, "Allie"), _p(conn, wid, "Donkey")
    tailender = _p(conn, wid, "Tail")
    # 2 matches: Allie bats (home) 50 off 50 AND bowls 75 balls taking 3; Donkey bowls 75 balls, 0 wickets.
    for _ in range(2):
        _match(conn, wid, comp, home, away,
               bats=[(allie, 50, 50)],
               away_bats=[(tailender, 20, 30)],
               home_bowls=[(allie, 75, 30, 3), (donkey, 75, 40, 0)])

    bat = _board(conn, wid, "rank_batting")
    bowl = _board(conn, wid, "rank_bowling")
    allr = _board(conn, wid, "rank_allrounder")

    expected = round(bat["Allie"]["points"] * bowl["Allie"]["points"] / 100.0, 1)
    assert allr["Allie"]["points"] == expected
    assert allr["Allie"]["batting_points"] == bat["Allie"]["points"]
    assert allr["Allie"]["bowling_points"] == bowl["Allie"]["points"]

    # 0-wicket bowler: no crash, finite index, undefined average term guarded (average is None)
    assert bowl["Donkey"]["average"] is None
    assert isinstance(bowl["Donkey"]["points"], float) and bowl["Donkey"]["points"] >= 0.0
