"""Ask OneStats (Phase 14) — natural language maps to a deterministic catalogue report; numbers come from
the engine; unmappable questions never fabricate. Requires a live DB; rolled back.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import ask, batting, bowling, competitions, matches, people
from onestats.domain import innings as inn

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
    conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a, 'ask') ON CONFLICT (id) DO NOTHING"), {"a": ACTOR})
    set_workspace(conn, wid)
    return wid


def _team(conn, wid, name):
    org = conn.execute(text("INSERT INTO organisation(workspace_id,name,kind) VALUES (:w,:n,'club') RETURNING id"),
                       {"w": wid, "n": name + " CC"}).scalar_one()
    return conn.execute(text("INSERT INTO team(workspace_id,organisation_id,name) VALUES (:w,:o,:n) RETURNING id"),
                        {"w": wid, "o": org, "n": name}).scalar_one()


@pytest.fixture
def seeded(conn):
    wid = _ws(conn, "ASK")
    comp = competitions.create_competition(conn, wid, ACTOR, name="League")
    se = conn.execute(text("INSERT INTO season(workspace_id,competition_id,label,start_date) "
                           "VALUES (:w,:c,'2024/25','2024-10-01') RETURNING id"), {"w": wid, "c": comp}).scalar_one()
    home, away = _team(conn, wid, "Home"), _team(conn, wid, "Away")
    cap = people.create_person(conn, wid, ACTOR, display_name="The Skipper")
    bat = people.create_person(conn, wid, ACTOR, display_name="Run Machine")
    bwl = people.create_person(conn, wid, ACTOR, display_name="Strike Bowler")
    ab = people.create_person(conn, wid, ACTOR, display_name="Opponent")
    for runs, wkts, gf in [(100, 3, False), (50, 5, True)]:
        mid = matches.create_match(conn, wid, ACTOR, competition_id=comp, season_id=se)
        matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True, captain_person_id=cap)
        matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
        if gf:
            matches.set_classification(conn, wid, ACTOR, mid, classification="grand_final")
        i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
        batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=bat, batting_position=1, runs=runs, dismissal_type="bowled")
        i2 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=2, batting_team_id=away, bowling_team_id=home)
        batting.create_entry(conn, wid, ACTOR, innings_id=i2, person_id=ab, batting_position=1, runs=5, dismissal_type="bowled")
        bowling.create_entry(conn, wid, ACTOR, innings_id=i2, person_id=bwl, legal_balls=48, runs_conceded=20, wickets=wkts)
        matches.set_result(conn, wid, ACTOR, mid, result_type="home_win", won_by_team_id=home)
        matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    return {"wid": wid}


def test_most_runs_question(seeded, conn):
    a = ask.answer(conn, seeded["wid"], "Who has scored the most runs for the club?")
    assert a["matched"] and a["report_id"] == "bat_most_runs"
    assert a["rows"][0]["player"] == "Run Machine" and a["rows"][0]["runs"] == 150


def test_most_wickets_in_grand_finals(seeded, conn):
    a = ask.answer(conn, seeded["wid"], "Who has the most wickets in grand finals?")
    assert a["matched"] and a["report_id"] == "bowl_most_wickets"
    assert "Grand Finals only" in a["scope"]
    assert a["rows"][0]["player"] == "Strike Bowler" and a["rows"][0]["wickets"] == 5   # GF-only (not 8)


def test_captain_win_pct_question(seeded, conn):
    a = ask.answer(conn, seeded["wid"], "Which captain has the best winning percentage?")
    assert a["matched"] and a["report_id"] == "capt_best_win_pct"


def test_consecutive_captain_wins_disambiguation(seeded, conn):
    a = ask.answer(conn, seeded["wid"], "Most consecutive wins as captain?")
    assert a["matched"] and a["report_id"] == "capt_consec_wins"
    assert a["rows"][0]["player"] == "The Skipper" and a["rows"][0]["streak"] == 2


def test_partnership_question_maps(seeded, conn):
    a = ask.answer(conn, seeded["wid"], "What is the highest partnership?")
    assert a["matched"] and a["report_id"] == "part_highest"


def test_unmappable_question_does_not_fabricate(seeded, conn):
    a = ask.answer(conn, seeded["wid"], "What is the meaning of life?")
    assert a["matched"] is False and "couldn't confidently map" in a["message"]
    assert isinstance(a["suggestions"], list)


def test_answer_carries_qualifications(seeded, conn):
    a = ask.answer(conn, seeded["wid"], "most runs")
    assert any("approved scorecards" in q for q in a["qualifications"])
    assert a["answer_summary"] and "Run Machine" in a["answer_summary"]
