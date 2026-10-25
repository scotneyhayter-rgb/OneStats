"""Phase 12, Stages 12.8/12.9 — batting partnerships + D12 bowling groups.

Bowling groups follow the user-confirmed worked example (combined wickets in matches all members played,
run outs excluded, each match once). Rolled back; skipped without a live DB.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import bowling, competitions, matches, people
from onestats.domain import innings as inn
from onestats.domain.stats import partnerships

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


def _bowl_match(conn, wid, comp, home, away, wk: dict):
    """A match where the given persons (on the away/bowling side) each bowl the given wickets."""
    mid = matches.create_match(conn, wid, ACTOR, competition_id=comp)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    for pid, w in wk.items():
        bowling.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=pid, legal_balls=24, runs_conceded=20, wickets=w)
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    return mid


def test_bowling_groups_d12(conn):
    wid = _ws(conn, "PT BOWL")
    comp = competitions.create_competition(conn, wid, ACTOR, name="League")
    home, away = _team(conn, wid, "Home"), _team(conn, wid, "Away")
    a = people.create_person(conn, wid, ACTOR, display_name="A")
    b = people.create_person(conn, wid, ACTOR, display_name="B")
    c = people.create_person(conn, wid, ACTOR, display_name="C")
    _bowl_match(conn, wid, comp, home, away, {a: 3, b: 0})            # M1 both play
    _bowl_match(conn, wid, comp, home, away, {a: 3, b: 3})            # M2 both play
    _bowl_match(conn, wid, comp, home, away, {a: 2, c: 3})            # M3 B absent -> excluded for {A,B}
    _bowl_match(conn, wid, comp, home, away, {a: 0, b: 4})            # M4 A on 0 still qualifies

    res = partnerships.bowling_groups(conn, {"workspace_id": wid}, size=2)
    ab = next(g for g in res["groups"] if set(g["members"]) == {str(a), str(b)})
    assert ab["total_wickets"] == 13 and ab["matches_together"] == 3 and ab["avg_per_match"] == 4.33
    # run outs are never counted; a combination where a member never played together has fewer matches
    bc = next((g for g in res["groups"] if set(g["members"]) == {str(b), str(c)}), None)
    assert bc is None or bc["matches_together"] == 0 or set(bc["members"]) == {str(b), str(c)}


def test_batting_partnerships(conn):
    wid = _ws(conn, "PT BAT")
    comp = competitions.create_competition(conn, wid, ACTOR, name="League")
    home, away = _team(conn, wid, "Home"), _team(conn, wid, "Away")
    p1 = people.create_person(conn, wid, ACTOR, display_name="Opener")
    p2 = people.create_person(conn, wid, ACTOR, display_name="Partner")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=comp)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    conn.execute(text("INSERT INTO partnership(workspace_id, innings_id, wicket_number, runs, unbroken, "
                      "player1_person_id, player2_person_id, origin) "
                      "VALUES (:w,:i,1,120,false,:a,:b,'calculated')"),
                 {"w": wid, "i": i1, "a": p1, "b": p2})
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    top = partnerships.batting_partnerships(conn, {"workspace_id": wid})
    assert top and top[0]["runs"] == 120 and {top[0]["batter1"], top[0]["batter2"]} == {str(p1), str(p2)}
    by_w = partnerships.batting_partnerships(conn, {"workspace_id": wid}, by_wicket=True)
    assert by_w[0]["wicket"] == 1 and by_w[0]["runs"] == 120
