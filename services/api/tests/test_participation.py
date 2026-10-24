"""Player participation & statistical attribution (Phase 6 foundation).

Rolled back in a single transaction (no data persists); skipped without a live DB. Pins the
attribution rules: performances follow the player's identity across clubs and are attributed to the
team actually represented in the match — a fill-in counts for that team, never the player's home
club, and a temporary affiliation never changes the primary registration or the attribution.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import (
    affiliations,
    batting,
    bowling,
    competitions,
    matches,
    participation,
    people,
)
from onestats.domain import (
    innings as inn,
)

settings = get_settings()
pytestmark = pytest.mark.skipif(
    not settings.db_configured, reason="no live database credential configured"
)

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
    set_workspace(conn, wid)
    return wid


def _org(conn, wid, name):
    return conn.execute(text("INSERT INTO organisation(workspace_id,name,kind) VALUES (:w,:n,'club') RETURNING id"), {"w": wid, "n": name}).scalar_one()


def _team(conn, wid, org, name):
    return conn.execute(text("INSERT INTO team(workspace_id,organisation_id,name) VALUES (:w,:o,:n) RETURNING id"), {"w": wid, "o": org, "n": name}).scalar_one()


def test_bill_smith_fill_in_attribution(conn):
    """Bill Smith is registered with Sandbox CC but fills in for Test Valley CC: 45 runs, 2 wickets,
    1 catch. Verify career counts it once, Test Valley gets it, Sandbox does not, his registration
    is unchanged, his profile shows the Test Valley appearance, and recalculating does not double it."""
    wid = _ws(conn, "PART BILL")
    cid = competitions.create_competition(conn, wid, ACTOR, name="RDCA")
    season = conn.execute(
        text("INSERT INTO season(workspace_id, competition_id, label, start_date, end_date) "
             "VALUES (:w,:c,'2026/27',:sf,:st) RETURNING id"),
        {"w": wid, "c": cid, "sf": dt.date(2026, 10, 1), "st": dt.date(2027, 3, 31)},
    ).scalar_one()
    sandbox = _org(conn, wid, "Sandbox Cricket Club")
    testvalley = _org(conn, wid, "Test Valley Cricket Club")
    sandbox_xi = _team(conn, wid, sandbox, "Sandbox 1st XI")
    tv_xi = _team(conn, wid, testvalley, "Test Valley 1st XI")

    bill = people.create_person(conn, wid, ACTOR, display_name="Bill Smith")
    # Bill is REGISTERED with Sandbox
    sandbox_reg = affiliations.create_affiliation(conn, wid, ACTOR, person_id=bill, organisation_id=sandbox,
                                                  team_id=sandbox_xi, role="player", valid_from=dt.date(2020, 9, 1))
    tv_opener = people.create_person(conn, wid, ACTOR, display_name="TV Opener")

    # Match in 2026/27: Test Valley v Sandbox. Bill FILLS IN for Test Valley.
    mid = matches.create_match(conn, wid, ACTOR, competition_id=cid, season_id=season)
    matches.set_team(conn, wid, ACTOR, mid, team_id=tv_xi, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=sandbox_xi, is_home=False)
    # innings 1: Test Valley batting -> Bill scores 45
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=tv_xi, bowling_team_id=sandbox_xi)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=bill, batting_position=1, runs=45, dismissal_type="not_out")
    # innings 2: Sandbox batting, Test Valley bowling -> Bill takes 2 wickets and holds 1 catch
    i2 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=2, batting_team_id=sandbox_xi, bowling_team_id=tv_xi)
    bowling.create_entry(conn, wid, ACTOR, innings_id=i2, person_id=bill, bowling_order=1, wickets=2, runs_conceded=20)
    batting.create_entry(conn, wid, ACTOR, innings_id=i2, person_id=tv_opener, batting_position=1, runs=10,
                         dismissal_type="caught", fielder_person_id=bill)

    # Fill-in = a TEMPORARY affiliation to Test Valley, bounded to the season; registration untouched.
    affiliations.create_affiliation(conn, wid, ACTOR, person_id=bill, organisation_id=testvalley, team_id=tv_xi,
                                    role="player", is_temporary=True, valid_from=dt.date(2026, 10, 1),
                                    valid_to=dt.date(2027, 3, 31), notes="fill-in")

    # --- career: counted ONCE, across clubs ---
    career = participation.player_career_totals(conn, bill)
    assert career["runs"] == 45 and career["wickets"] == 2 and career["catches"] == 1 and career["matches"] == 1

    # --- attributed to the team REPRESENTED (Test Valley), not his home club ---
    tv = participation.player_team_totals(conn, bill, tv_xi, season)
    assert tv["runs"] == 45 and tv["wickets"] == 2 and tv["catches"] == 1
    # Sandbox (his registered club) gets NOTHING from this fill-in appearance
    sb = participation.player_team_totals(conn, bill, sandbox_xi, season)
    assert sb["runs"] == 0 and sb["wickets"] == 0 and sb["catches"] == 0
    # Test Valley's team totals include it; Sandbox's do not
    assert participation.team_totals(conn, tv_xi, season)["runs"] >= 45
    sandbox_team = participation.team_totals(conn, sandbox_xi, season)
    assert sandbox_team["runs"] == 10  # only its own opener's runs, none of Bill's

    # --- his original registration is UNCHANGED (still Sandbox, not temporary) ---
    reg = affiliations.get_affiliation(conn, sandbox_reg)
    assert reg["organisation_id"] == sandbox and reg["is_temporary"] is False

    # --- profile shows the Test Valley appearance (team he represented) ---
    apps = participation.player_appearances(conn, bill)
    assert len(apps) == 1 and apps[0]["team_id"] == tv_xi and apps[0]["organisation_id"] == testvalley

    # --- recalculating does not duplicate ---
    career_again = participation.player_career_totals(conn, bill)
    assert career_again == career


def test_team_season_players_affiliation_and_appearances(conn):
    wid = _ws(conn, "PART ROSTER")
    cid = competitions.create_competition(conn, wid, ACTOR, name="RDCA")
    season = conn.execute(
        text("INSERT INTO season(workspace_id, competition_id, label, start_date, end_date) "
             "VALUES (:w,:c,'2026/27',:sf,:st) RETURNING id"),
        {"w": wid, "c": cid, "sf": dt.date(2026, 10, 1), "st": dt.date(2027, 3, 31)},
    ).scalar_one()
    org = _org(conn, wid, "Club")
    team = _team(conn, wid, org, "1st XI")
    other = _team(conn, wid, org, "2nd XI")

    affiliated = people.create_person(conn, wid, ACTOR, display_name="Affiliated Player")
    affiliations.create_affiliation(conn, wid, ACTOR, person_id=affiliated, organisation_id=org, team_id=team,
                                    role="player", valid_from=dt.date(2026, 10, 1))
    appeared = people.create_person(conn, wid, ACTOR, display_name="Appeared Player")
    elsewhere = people.create_person(conn, wid, ACTOR, display_name="Unrelated Player")

    mid = matches.create_match(conn, wid, ACTOR, competition_id=cid, season_id=season)
    matches.set_team(conn, wid, ACTOR, mid, team_id=team, is_home=True)
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=team)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=appeared, batting_position=1, runs=5)

    roster = participation.team_season_players(conn, team, season)
    ids = {r["person_id"] for r in roster}
    assert affiliated in ids and appeared in ids  # affiliation + appearance both included
    assert elsewhere not in ids                   # unrelated player not suggested
    # flags are set correctly
    by_id = {r["person_id"]: r for r in roster}
    assert by_id[affiliated]["affiliated"] is True
    assert by_id[appeared]["appeared"] is True
    # the other team's roster does not include this team's appearance
    assert appeared not in {r["person_id"] for r in participation.team_season_players(conn, other, season)}
