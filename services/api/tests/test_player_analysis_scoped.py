"""Club-scoped player analysis & match history (live DB, rolled back; skipped without a credential).

Proves ``player_analysis(organisation_id=...)`` and ``match_history(organisation_id=...)`` reflect ONLY the
matches the player featured in for that one club — never mixing in another club's figures. That guarantee is
what lets a club-scoped published profile carry the full analysis reports safely.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import batting as bat
from onestats.domain import competitions, matches, people
from onestats.domain import innings as inn
from onestats.domain.records import player_analysis as pa
from onestats.domain.records import player_profile as pp

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
    wid = conn.execute(
        text("INSERT INTO workspace(name, type) VALUES (:n,'club') RETURNING id"), {"n": name}
    ).scalar_one()
    set_workspace(conn, wid)
    return wid


def _org(conn, wid, name):
    return conn.execute(
        text("INSERT INTO organisation(workspace_id, name, kind) VALUES (:w,:n,'club') RETURNING id"),
        {"w": wid, "n": name},
    ).scalar_one()


def _team(conn, wid, org, name):
    return conn.execute(
        text("INSERT INTO team(workspace_id, organisation_id, name) VALUES (:w,:o,:n) RETURNING id"),
        {"w": wid, "o": org, "n": name},
    ).scalar_one()


def _approved_innings(conn, wid, cid, club_org, club_name, opp_name, person, runs, md):
    """One approved, statistics-eligible match in which ``person`` bats for a team of ``club_org``."""
    mine = _team(conn, wid, club_org, club_name)
    opp = _team(conn, wid, _org(conn, wid, opp_name + " Org"), opp_name)
    mid = matches.create_match(conn, wid, ACTOR, competition_id=cid, match_date=md)
    matches.set_team(conn, wid, ACTOR, mid, team_id=mine, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=opp, is_home=False)
    iid = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1,
                             batting_team_id=mine, bowling_team_id=opp)
    bat.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=person, batting_position=1,
                     runs=runs, dismissal_type="bowled")
    matches.update_match(conn, wid, ACTOR, mid, include_in_statistics=True)
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    return mid


def test_player_analysis_reflects_only_the_chosen_club(conn):
    wid = _ws(conn, "SCOPE WS")
    cid = competitions.create_competition(conn, wid, ACTOR, name="League")
    p = people.create_person(conn, wid, ACTOR, display_name="Dual Clubber")
    club_a = _org(conn, wid, "Alpha CC")
    club_b = _org(conn, wid, "Beta CC")
    _approved_innings(conn, wid, cid, club_a, "Alpha 1st XI", "Rivals A", p, 101, date(2020, 1, 1))
    _approved_innings(conn, wid, cid, club_b, "Beta 1st XI", "Rivals B", p, 40, date(2021, 1, 1))

    # Whole career sees both innings.
    whole = pa.player_analysis(conn, wid, p)
    assert sorted(i["runs"] for i in whole["scores"]["innings"]) == [40, 101]

    # Scoped to Alpha: only the 101 for Alpha — Beta's 40 must not appear anywhere.
    only_a = pa.player_analysis(conn, wid, p, organisation_id=club_a)
    assert [i["runs"] for i in only_a["scores"]["innings"]] == [101]
    assert [b["runs"] for b in only_a["best_batting"]] == [101]

    # Scoped to Beta: only the 40.
    only_b = pa.player_analysis(conn, wid, p, organisation_id=club_b)
    assert [i["runs"] for i in only_b["scores"]["innings"]] == [40]


def test_match_history_reflects_only_the_chosen_club(conn):
    wid = _ws(conn, "SCOPE WS2")
    cid = competitions.create_competition(conn, wid, ACTOR, name="League")
    p = people.create_person(conn, wid, ACTOR, display_name="Dual Clubber 2")
    club_a = _org(conn, wid, "Alpha CC")
    club_b = _org(conn, wid, "Beta CC")
    _approved_innings(conn, wid, cid, club_a, "Alpha 1st XI", "Rivals A", p, 55, date(2020, 1, 1))
    _approved_innings(conn, wid, cid, club_b, "Beta 1st XI", "Rivals B", p, 22, date(2021, 1, 1))

    assert len(pp.match_history(conn, wid, p)) == 2
    a_only = pp.match_history(conn, wid, p, organisation_id=club_a)
    assert len(a_only) == 1 and a_only[0]["runs"] == 55
