"""Phase 13, Stages 13.3/13.4 — all-time records + seasonal leaders. Rolled back; skipped without a DB."""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import batting, bowling, competitions, matches, people
from onestats.domain import innings as inn
from onestats.domain.records import records

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


def test_all_time_records_holder_and_ties(conn):
    wid = _ws(conn, "REC")
    comp = competitions.create_competition(conn, wid, ACTOR, name="L")
    season = conn.execute(text("INSERT INTO season(workspace_id,competition_id,label,start_date) "
                               "VALUES (:w,:c,'2024/25',:d) RETURNING id"),
                          {"w": wid, "c": comp, "d": dt.date(2024, 10, 1)}).scalar_one()
    home, away = _team(conn, wid, "H"), _team(conn, wid, "A")
    star = people.create_person(conn, wid, ACTOR, display_name="Star Batter")
    rival = people.create_person(conn, wid, ACTOR, display_name="Rival")
    bowler = people.create_person(conn, wid, ACTOR, display_name="Spearhead")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=comp, season_id=season)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=star, batting_position=1,
                         runs=150, balls_faced=120, dismissal_type="not_out")
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=rival, batting_position=2,
                         runs=40, balls_faced=50, dismissal_type="bowled", bowler_person_id=bowler)
    bowling.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=bowler, legal_balls=30, runs_conceded=25, wickets=6)
    # a recorded partnership between the two batters, to check the record names BOTH of them
    conn.execute(text("INSERT INTO partnership(workspace_id, innings_id, wicket_number, runs, "
                      "player1_person_id, player2_person_id, unbroken) VALUES (:w,:i,1,55,:a,:b,false)"),
                 {"w": wid, "i": i1, "a": star, "b": rival})
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")

    rec = records.all_time_records(conn, wid, {"workspace_id": wid})
    assert rec["most_runs"]["holder"]["player"] == "Star Batter" and rec["most_runs"]["value"] == 150
    # the highest-partnership record names both batsmen (not just the value)
    hp = rec["highest_partnership"]
    assert hp["value"] == 55 and hp["holder"]["player"] == "Star Batter & Rival"
    assert hp["holder"]["batter1_name"] == "Star Batter" and hp["holder"]["batter2_name"] == "Rival"
    assert hp["ranking"][0]["player"] == "Star Batter & Rival"

    # records show the player's club (derived from their appearances). Both batted for team "H" (org "H CC").
    assert rec["most_runs"]["holder"]["club"] == "H CC"
    assert rec["most_runs"]["ranking"][0]["club"] == "H CC"
    assert hp["holder"]["club"] == "H CC"                       # same club → shown once
    # global mode lists every club represented; here each player has one club, so it matches primary
    recg = records.all_time_records(conn, wid, {"workspace_id": wid}, club_mode="global")
    assert recg["most_runs"]["holder"]["club"] == "H CC"
    assert rec["highest_score"]["value"] == 150
    assert rec["most_wickets"]["holder"]["player"] == "Spearhead" and rec["most_wickets"]["value"] == 6
    assert rec["most_five_fors"]["value"] == 1
    assert rec["most_runs"]["holder"]["tied"] is False

    leaders = records.seasonal_leaders(conn, wid)
    s = next(x for x in leaders if x["label"] == "2024/25")
    assert s["leading_run_scorer"]["player"] == "Star Batter" and s["leading_run_scorer"]["value"] == 150
    assert s["leading_wicket_taker"]["player"] == "Spearhead"


def test_reclassify_grand_final_refreshes_stats_split(conn):
    """Marking an already-approved match a grand final refreshes the stats ledger, so the player's
    grand-final figures appear immediately — no re-approval needed."""
    from onestats.domain.stats import engine
    wid = _ws(conn, "REC GF SPLIT")
    comp = competitions.create_competition(conn, wid, ACTOR, name="L")
    home, away = _team(conn, wid, "H"), _team(conn, wid, "A")
    star = people.create_person(conn, wid, ACTOR, display_name="GF Hero")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=comp)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=star, batting_position=1,
                         runs=80, balls_faced=60, dismissal_type="not_out")
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")   # approved while still unclassified
    gf = {"workspace_id": wid, "split": "grand_final"}
    assert int(engine.person_batting(conn, gf, star).get("runs") or 0) == 0   # not a grand final yet
    matches.set_classification(conn, wid, ACTOR, mid, classification="grand_final")
    assert engine.person_batting(conn, gf, star)["runs"] == 80     # ledger refreshed, no re-approval
