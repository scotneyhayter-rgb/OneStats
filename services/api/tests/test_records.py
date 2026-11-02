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


def test_most_run_outs_record_ranks_by_involvements(conn):
    """The 'Most Run Outs' all-time record ranks by run-out involvements (primary + assisting second
    fielder), matching CricketStatz. A player who only ever assists (recorded as the run-out's second
    fielder, i.e. the imported bowler_person_id) must still be able to hold/tie the record; under the old
    primary-only ranking they had run_outs=0 and were invisible."""
    wid = _ws(conn, "REC RO")
    comp = competitions.create_competition(conn, wid, ACTOR, name="L")
    home, away = _team(conn, wid, "H"), _team(conn, wid, "A")
    prim = people.create_person(conn, wid, ACTOR, display_name="Primary Fielder")
    second = people.create_person(conn, wid, ACTOR, display_name="Second Fielder")
    victim = people.create_person(conn, wid, ACTOR, display_name="Run-out Victim")
    for _ in range(2):   # two run-outs, same two fielders: prim primary, second as the 'bowler' field
        mid = matches.create_match(conn, wid, ACTOR, competition_id=comp)
        matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
        matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
        i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1,
                                batting_team_id=away, bowling_team_id=home)
        batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=victim, batting_position=1,
                             runs=10, balls_faced=20, dismissal_type="run_out",
                             fielder_person_id=prim, bowler_person_id=second)
        matches.set_approval(conn, wid, ACTOR, mid, status="approved")

    rec = records.all_time_records(conn, wid, {"workspace_id": wid})
    ro = rec["most_run_outs"]
    assert ro["value"] == 2                    # involvements, not the 0-vs-2 primary split
    assert ro["holder"]["tied"] is True
    holders = {ro["holder"]["subject_id"]} | {t["subject_id"] for t in ro["ties"]}
    assert str(second) in holders              # the assisting fielder now holds the record (was invisible)
    assert str(prim) in holders
    assert str(victim) not in holders


def _org_of(conn, team_id):
    return conn.execute(text("SELECT organisation_id FROM team WHERE id = :t"), {"t": team_id}).scalar_one()


def test_club_lens_and_new_records(conn):
    """The records engine exposes Best Bowling in an Innings, career/season partnership aggregates and a
    per-wicket partnership list, and the organisation_id 'club lens' restricts records to one club's
    performances. Upcoming milestones name the player."""
    from onestats.domain.records import milestones
    from onestats.domain.stats import records_detail
    wid = _ws(conn, "REC LENS")
    comp = competitions.create_competition(conn, wid, ACTOR, name="L")
    season = conn.execute(text("INSERT INTO season(workspace_id,competition_id,label,start_date) "
                               "VALUES (:w,:c,'2024/25',:d) RETURNING id"),
                          {"w": wid, "c": comp, "d": dt.date(2024, 10, 1)}).scalar_one()
    home, away = _team(conn, wid, "Home"), _team(conn, wid, "Away")
    home_org, away_org = _org_of(conn, home), _org_of(conn, away)
    hbat1 = people.create_person(conn, wid, ACTOR, display_name="Home One")
    hbat2 = people.create_person(conn, wid, ACTOR, display_name="Home Two")
    abat = people.create_person(conn, wid, ACTOR, display_name="Away Bat")
    abowl = people.create_person(conn, wid, ACTOR, display_name="Away Bowler")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=comp, season_id=season)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    # innings 1: Home bats (a 120-run opening stand); Away's bowler takes 7/30
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=hbat1, batting_position=1, runs=70, balls_faced=90, dismissal_type="not_out")
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=hbat2, batting_position=2, runs=55, balls_faced=60, dismissal_type="bowled", bowler_person_id=abowl)
    bowling.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=abowl, legal_balls=60, runs_conceded=30, wickets=7)
    conn.execute(text("INSERT INTO partnership(workspace_id, innings_id, wicket_number, runs, "
                      "player1_person_id, player2_person_id, unbroken) VALUES (:w,:i,1,120,:a,:b,false)"),
                 {"w": wid, "i": i1, "a": hbat1, "b": hbat2})
    # innings 2: Away bats
    i2 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=2, batting_team_id=away, bowling_team_id=home)
    batting.create_entry(conn, wid, ACTOR, innings_id=i2, person_id=abat, batting_position=1, runs=40, balls_faced=50, dismissal_type="not_out")
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")

    rec = records.all_time_records(conn, wid, {"workspace_id": wid})
    # new records are present with a figure/holder
    assert rec["best_bowling_innings"]["value"] == "7-30"
    assert rec["best_bowling_innings"]["holder"]["player"] == "Away Bowler"
    assert rec["partnership_aggregate_career"]["value"] == 120
    assert "Home One" in rec["partnership_aggregate_career"]["holder"]["player"]
    assert rec["partnership_aggregate_season"]["value"] == 120
    assert "(2024/25)" in rec["partnership_aggregate_season"]["holder"]["player"]

    # club lens: scoping to the Home club shows the Home batter's runs, not the Away batter's
    rec_home = records.all_time_records(conn, wid, {"workspace_id": wid, "organisation_id": home_org})
    assert rec_home["most_runs"]["holder"]["player"] == "Home One"
    rec_away = records.all_time_records(conn, wid, {"workspace_id": wid, "organisation_id": away_org})
    assert rec_away["most_runs"]["holder"]["player"] == "Away Bat"       # Home players excluded by the lens
    assert rec_away["best_bowling_innings"]["holder"]["player"] == "Away Bowler"
    assert rec_away["partnership_aggregate_career"]["holder"] is None     # no Away partnership in scope

    # per-wicket partnership list
    byw = records_detail.highest_partnership_by_wicket(conn, {"workspace_id": wid})
    assert byw[0]["wicket"] == 1 and byw[0]["runs"] == 120

    # upcoming milestones name the player (Home One is on 70, within window of 100)
    up = milestones.upcoming_for_workspace(conn, wid, window=40)
    assert any(u["player"] == "Home One" and u["threshold"] == 100 for u in up)


def test_best_bowling_in_a_match_record_uses_runs_tiebreak(conn):
    """The 'Best Bowling in a Match' all-time record is a figure ranked by most wickets THEN fewest runs
    conceded — not the bare wicket count. Two bowlers on equal wickets must be split by runs, and the
    record value is shown as 'W-R', with the lower-runs bowler the sole holder (not a tie)."""
    wid = _ws(conn, "REC BBM")
    comp = competitions.create_competition(conn, wid, ACTOR, name="L")
    home, away = _team(conn, wid, "H"), _team(conn, wid, "A")
    frugal = people.create_person(conn, wid, ACTOR, display_name="Frugal Quick")
    costly = people.create_person(conn, wid, ACTOR, display_name="Costly Quick")
    for bowler, conceded in ((frugal, 20), (costly, 40)):   # same 5 wickets, different runs
        mid = matches.create_match(conn, wid, ACTOR, competition_id=comp)
        matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
        matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
        i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1,
                                batting_team_id=home, bowling_team_id=away)
        bowling.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=bowler,
                             legal_balls=60, runs_conceded=conceded, wickets=5)
        matches.set_approval(conn, wid, ACTOR, mid, status="approved")

    rec = records.all_time_records(conn, wid, {"workspace_id": wid})
    bbm = rec["best_match_bowling"]
    assert bbm["value"] == "5-20"                      # figure, not bare "5"
    assert bbm["holder"]["player"] == "Frugal Quick"   # fewer runs wins
    assert bbm["holder"]["tied"] is False              # runs break the wicket-only tie
    assert [r["value"] for r in bbm["ranking"][:2]] == ["5-20", "5-40"]


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
