"""Data-quality scorer-error checks (audit P3)."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import batting, bowling, competitions, data_quality, matches, people
from onestats.domain import innings as inn

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


def test_scan_flags_scorer_errors_without_inventing_data(conn):
    wid = _ws(conn, "DQ")
    cid = competitions.create_competition(conn, wid, ACTOR, name="League")
    home, away = _team(conn, wid, "Home"), _team(conn, wid, "Away")
    bowler = people.create_person(conn, wid, ACTOR, display_name="Bowler")
    bat1 = people.create_person(conn, wid, ACTOR, display_name="Runout victim")
    bat2 = people.create_person(conn, wid, ACTOR, display_name="Caught victim")
    m = matches.create_match(conn, wid, ACTOR, competition_id=cid)
    matches.set_team(conn, wid, ACTOR, m, team_id=home, is_home=True)   # no captain/keeper on either side
    matches.set_team(conn, wid, ACTOR, m, team_id=away, is_home=False)
    i = inn.create_innings(conn, wid, ACTOR, match_id=m, inns_number=1, batting_team_id=home, bowling_team_id=away)
    # a run-out with no fielder, and a catch where bowler == fielder (should be c&b)
    batting.create_entry(conn, wid, ACTOR, innings_id=i, person_id=bat1, batting_position=1, runs=5,
                         dismissal_type="run_out")  # fielder missing
    batting.create_entry(conn, wid, ACTOR, innings_id=i, person_id=bat2, batting_position=2, runs=3,
                         dismissal_type="caught", bowler_person_id=bowler, fielder_person_id=bowler)  # bowler==fielder
    bowling.create_entry(conn, wid, ACTOR, innings_id=i, person_id=bowler, legal_balls=12, runs_conceded=8, wickets=2)

    out = data_quality.scan(conn, wid)
    counts = {c["key"]: c["count"] for c in out["checks"]}
    assert counts["missing_fielder"] == 1        # the run-out
    assert counts["bowler_is_fielder"] == 1      # the catch where bowler took it
    assert counts["captain_missing"] == 2        # both sides
    assert counts["keeper_missing"] == 2
    assert out["total_issues"] >= 6
    # the issue carries the match for drill-down, and nothing was changed
    mf = next(c for c in out["checks"] if c["key"] == "missing_fielder")
    assert mf["sample"][0]["match_id"] == str(m)
    assert out["ok"] is False


def test_scan_can_scope_to_one_match(conn):
    wid = _ws(conn, "DQ SCOPE")
    cid = competitions.create_competition(conn, wid, ACTOR, name="League")
    home, away = _team(conn, wid, "Home"), _team(conn, wid, "Away")
    bat = people.create_person(conn, wid, ACTOR, display_name="Victim")
    # two matches, each with a fielderless run-out
    mids = []
    for _ in range(2):
        m = matches.create_match(conn, wid, ACTOR, competition_id=cid)
        matches.set_team(conn, wid, ACTOR, m, team_id=home, is_home=True)
        matches.set_team(conn, wid, ACTOR, m, team_id=away, is_home=False)
        i = inn.create_innings(conn, wid, ACTOR, match_id=m, inns_number=1, batting_team_id=home, bowling_team_id=away)
        batting.create_entry(conn, wid, ACTOR, innings_id=i, person_id=bat, batting_position=1, runs=1, dismissal_type="run_out")
        mids.append(m)
    whole = {c["key"]: c["count"] for c in data_quality.scan(conn, wid)["checks"]}
    one = {c["key"]: c["count"] for c in data_quality.scan(conn, wid, match_id=mids[0])["checks"]}
    assert whole["missing_fielder"] == 2      # both matches, workspace-wide
    assert one["missing_fielder"] == 1        # scoped to a single match
