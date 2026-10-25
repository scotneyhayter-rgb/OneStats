"""Approved forfeit policy (deliverable 24 §24.2a) — regression tests.

Rules: a forfeit may count for TEAM results, competition points and ladders; but a forfeit where NO
cricket was played must NOT create individual player appearances or captaincy appearances, nor inflate
captaincy wins/losses/streaks/winning-percentage. A partly-played match later awarded by forfeit keeps its
verified appearances and captaincy. Team outcomes and individual participation stay separate.

Requires a live DB; rolled back.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import batting, competitions, matches, people
from onestats.domain import innings as inn
from onestats.domain.stats import competition_points, engine

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


def _setup(conn, name):
    wid = _ws(conn, name)
    comp = competitions.create_competition(conn, wid, ACTOR, name="League")
    se = conn.execute(text("INSERT INTO season(workspace_id,competition_id,label,start_date) "
                           "VALUES (:w,:c,'2024/25','2024-10-01') RETURNING id"), {"w": wid, "c": comp}).scalar_one()
    home, away = _team(conn, wid, "Home"), _team(conn, wid, "Away")
    cap = people.create_person(conn, wid, ACTOR, display_name="Named Captain")
    return wid, comp, se, home, away, cap


def test_full_forfeit_no_play_team_result_but_no_individual_stats(conn):
    """Cases 1, 2 & 4: a full forfeit with no play gives the TEAM the win and competition points, but
    creates NO player appearance and NO captaincy appearance for the named captain."""
    wid, comp, se, home, away, cap = _setup(conn, "FFT NOPLAY")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=comp, season_id=se)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True, captain_person_id=cap)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    matches.set_result(conn, wid, ACTOR, mid, result_type="forfeit", won_by_team_id=home)   # no innings/entries
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    f = {"workspace_id": wid}
    # team result recorded (home win)
    teams = engine.team_records(conn, f)
    home_row = next(r for r in teams if r["subject_id"] == str(home))
    assert home_row["wins"] == 1 and home_row["played"] == 1
    # competition points awarded to the team
    lad = competition_points.ladder(conn, wid, competition_id=comp)
    pts = next(s for s in lad["standings"] if s["team_id"] == str(home))
    assert pts["points"] > 0 and pts["wins"] == 1
    # NO individual appearance, NO captaincy for the named captain
    assert engine.person_participation(conn, f, cap)["matches"] == 0
    assert engine.person_captaincy(conn, f, cap)["captained"] == 0


def test_partly_played_forfeit_preserves_participation(conn):
    """Cases 3 & 5: a match partly played then awarded by forfeit keeps verified appearances and
    captaincy (the captain who actually batted is still credited)."""
    wid, comp, se, home, away, cap = _setup(conn, "FFT PARTLY")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=comp, season_id=se)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True, captain_person_id=cap)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=cap, batting_position=1, runs=25,
                         dismissal_type="not_out")                                   # some play happened
    matches.set_result(conn, wid, ACTOR, mid, result_type="forfeit", won_by_team_id=home)
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    f = {"workspace_id": wid}
    # the captain actually played -> appearance AND captaincy preserved
    assert engine.person_participation(conn, f, cap)["matches"] == 1
    assert engine.person_captaincy(conn, f, cap)["captained"] == 1
    assert engine.person_batting(conn, f, cap)["runs"] == 25


def test_normal_match_unaffected_by_forfeit_logic(conn):
    """Case 6 (control): an ordinary approved result still creates appearances and captaincy, proving the
    forfeit exclusion does not leak into normal matches."""
    wid, comp, se, home, away, cap = _setup(conn, "FFT NORMAL")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=comp, season_id=se)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True, captain_person_id=cap)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=cap, batting_position=1, runs=40,
                         dismissal_type="bowled")
    matches.set_result(conn, wid, ACTOR, mid, result_type="home_win", won_by_team_id=home)
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    f = {"workspace_id": wid}
    assert engine.person_participation(conn, f, cap)["matches"] == 1
    assert engine.person_captaincy(conn, f, cap)["captained"] == 1 and engine.person_captaincy(conn, f, cap)["wins"] == 1
