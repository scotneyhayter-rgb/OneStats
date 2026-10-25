"""Phase 12, Stage 12.12 — competition points & ladders. Rolled back; skipped without a live DB."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import competitions, matches, playing_conditions
from onestats.domain.stats import competition_points

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


def _match(conn, wid, comp, home, away, *, result, won_by=None, home_bonus=None):
    mid = matches.create_match(conn, wid, ACTOR, competition_id=comp)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True, bonus_points=home_bonus)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    matches.set_result(conn, wid, ACTOR, mid, result_type=result, won_by_team_id=won_by)
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    return mid


def test_ladder_default_scheme(conn):
    wid = _ws(conn, "LADDER")
    comp = competitions.create_competition(conn, wid, ACTOR, name="League")
    home, away = _team(conn, wid, "Home"), _team(conn, wid, "Away")
    _match(conn, wid, comp, home, away, result="home_win", won_by=home, home_bonus=1)  # win=4 + bonus 1 = 5
    _match(conn, wid, comp, home, away, result="tie")                                   # tie = 2 each
    lad = competition_points.ladder(conn, wid, competition_id=comp)
    by_team = {s["team_id"]: s for s in lad["standings"]}
    assert by_team[str(home)]["points"] == 7.0 and by_team[str(home)]["wins"] == 1 and by_team[str(home)]["ties"] == 1
    assert by_team[str(away)]["points"] == 2.0 and by_team[str(away)]["losses"] == 1
    assert lad["standings"][0]["team_id"] == str(home) and lad["standings"][0]["position"] == 1


def test_ladder_uses_configured_scheme(conn):
    wid = _ws(conn, "LADDER CFG")
    comp = competitions.create_competition(conn, wid, ACTOR, name="Historical")
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="competition", target_id=comp,
                                      points={"win": 6, "loss": 0, "tie": 3, "draw": 3, "no_result": 1})
    home, away = _team(conn, wid, "H"), _team(conn, wid, "A")
    _match(conn, wid, comp, home, away, result="home_win", won_by=home)
    lad = competition_points.ladder(conn, wid, competition_id=comp)
    assert lad["scheme"]["win"] == 6
    assert next(s for s in lad["standings"] if s["team_id"] == str(home))["points"] == 6.0  # configured, not default 4


def test_unknown_result_excluded(conn):
    wid = _ws(conn, "LADDER UNK")
    comp = competitions.create_competition(conn, wid, ACTOR, name="L")
    home, away = _team(conn, wid, "H"), _team(conn, wid, "A")
    _match(conn, wid, comp, home, away, result="unknown")
    lad = competition_points.ladder(conn, wid, competition_id=comp)
    h = next(s for s in lad["standings"] if s["team_id"] == str(home))
    assert h["played"] == 1 and h["unknown"] == 1 and h["points"] == 0.0  # not assumed a result
