"""Live CricketStatz scorecard-import tests (Phase 6, Stage 8b).

Rolled back in a single transaction (no data persists); skipped without a live DB. Runs as the
least-privilege ``onestats_app`` role under FORCE RLS. Uses a **synthetic** CricketStatz-shaped
JSON fixture (the nested ``cricket_Innings`` scorecard body) — the genuine export is never used in
tests. Covers: innings/batting/bowling/extras/fall-of-wicket promotion into the existing scorecard
models; dismissal TYPE left unresolved while the raw Howout code is preserved; player references
resolved via the people import's source identities; empty padding rows skipped; historically
incomplete cards still imported; idempotent re-import; and the unresolved-Howout report.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import imports, people

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "11111111-1111-1111-1111-111111111111"
SS = "cricket_statz"

# minimal structural + scorecard payload in the genuine nested shape (fake ids)
PAYLOAD = {
    "clubs": [{"ClubID": 1, "Name": "Alpha CC"}],
    "teams": [{"TeamID": 100, "Name": "Alpha 1st", "ClubID": 1},
              {"TeamID": 200, "Name": "Beta 1st", "ClubID": 1}],
    "venues": [{"GroundID": 10, "Name": "Alpha Oval"}],
    "divisions": [{"GradeID": 50, "Name": "B Grade"}],
    "matches": [{"MatchID": 500, "HomeTeam": 100, "AwayTeam": 200, "DatePlayed": "2024-01-06",
                 "Ground": 10, "Grade": 50, "Result": 1, "round": "1", "matchtype": 1}],
    "innings": [{"MatchID": 500, "cricket_Innings": [
        {"InningsID": 700, "InnsNumber": 1, "battingteam": 100, "bowlingteam": 200,
         "iresult": 1, "Byes": 4, "Legbyes": 2, "Noballs": 1, "Wides": 3},
    ]}],
    "batting": [{"MatchID": 500, "cricket_Innings": [
        {"InningsID": 700, "InnsNumber": 1, "cricket_batting": [
            {"Batpos": 1, "BatsmanID": 10, "Howout": 2, "Bowler": 20, "Fielder": 0, "Score": 38,
             "Balls": 41, "mins": 60, "sixes": 1, "fours": 5, "FOW": 40, "FOWPos": 1,
             "FOWBatID": 10, "FOWOvers": 12.3},
            {"Batpos": 2, "BatsmanID": 11, "Howout": 99, "Bowler": 0, "Fielder": 0, "Score": 12,
             "Balls": 0, "mins": 0, "sixes": 0, "fours": 0, "FOW": 0, "FOWPos": 2,
             "FOWBatID": 0, "FOWOvers": 0.0},  # Howout 99 = unknown code; still imports
            {"Batpos": 3, "BatsmanID": 0, "Howout": 0, "Bowler": 0, "Fielder": 0, "Score": 0,
             "Balls": 0, "mins": 0, "sixes": 0, "fours": 0, "FOW": 0, "FOWPos": 3,
             "FOWBatID": 0, "FOWOvers": 0.0},  # padding slot -> skipped
        ]},
    ]}],
    "bowling": [{"MatchID": 500, "cricket_Innings": [
        {"InningsID": 700, "InnsNumber": 1, "cricket_bowling": [
            {"bowlerID": 20, "Maidens": 1, "Overs": 8.0, "Wickets": 2, "RunsA": 30, "wides": 1, "noballs": 0},
            {"bowlerID": 0, "Maidens": 0, "Overs": 0.0, "Wickets": 0, "RunsA": 0, "wides": 0, "noballs": 0},
        ]},
    ]}],
}


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
    wid = conn.execute(text("INSERT INTO workspace(name, type) VALUES (:n,'club') RETURNING id"),
                       {"n": name}).scalar_one()
    set_workspace(conn, wid)
    return wid


def _seed_players(conn, wid):
    """Create the two people with CricketStatz source identities so scorecard refs resolve."""
    p1 = people.create_person(conn, wid, ACTOR, display_name="Batter Ten", source_system=SS, source_ref="10")
    p2 = people.create_person(conn, wid, ACTOR, display_name="Bowler Twenty", source_system=SS, source_ref="20")
    return p1, p2


def _promote(conn, wid):
    bid = imports.parse_and_stage(conn, wid, ACTOR, payload=PAYLOAD)["batch_id"]
    return bid, imports.promote_batch(conn, wid, ACTOR, bid)


def test_scorecard_promotes_into_existing_models(conn):
    wid = _ws(conn, "SC WS1")
    p1, p2 = _seed_players(conn, wid)
    _, res = _promote(conn, wid)
    assert res["created"]["innings"] == 1
    assert res["created"]["batting_entry"] == 2          # two real batters; padding skipped
    assert res["created"]["bowling_entry"] == 1          # one real bowler; padding skipped
    assert res["created"]["fall_of_wicket"] == 1

    inn = conn.execute(text("SELECT id, byes, legbyes, wides, noballs, batting_team_id, bowling_team_id "
                            "FROM innings WHERE source_ref = '700'")).mappings().one()
    assert (inn["byes"], inn["legbyes"], inn["wides"], inn["noballs"]) == (4, 2, 3, 1)  # extras preserved
    t100 = conn.execute(text("SELECT id FROM team WHERE source_ref = '100'")).scalar_one()
    t200 = conn.execute(text("SELECT id FROM team WHERE source_ref = '200'")).scalar_one()
    assert inn["batting_team_id"] == t100 and inn["bowling_team_id"] == t200

    bat = conn.execute(text("SELECT person_id, runs, balls_faced, fours, sixes, dismissal_type, "
                            "dismissal_source_code, bowler_person_id FROM batting_entry "
                            "WHERE source_ref = '700:1'")).mappings().one()
    assert bat["runs"] == 38 and bat["balls_faced"] == 41 and bat["fours"] == 5
    assert bat["person_id"] == p1 and bat["bowler_person_id"] == p2      # resolved via source identity
    assert bat["dismissal_type"] is None                                # UNRESOLVED — never guessed
    assert bat["dismissal_source_code"] == "2"                          # raw Howout preserved

    bowl = conn.execute(text("SELECT person_id, wickets, runs_conceded, maidens, wides "
                             "FROM bowling_entry WHERE source_ref = '700:20:1'")).mappings().one()
    assert bowl["wickets"] == 2 and bowl["runs_conceded"] == 30 and bowl["person_id"] == p2

    fow = conn.execute(text("SELECT wicket_number, team_score, dismissed_person_id "
                            "FROM fall_of_wicket WHERE source_ref = '700:1'")).mappings().one()
    assert fow["wicket_number"] == 1 and fow["team_score"] == 40 and fow["dismissed_person_id"] == p1


def test_unknown_howout_code_still_imports_figures(conn):
    """A batter with an unknown/ambiguous Howout code (99) still imports runs etc.; the dismissal is
    left unresolved and the raw code preserved — the card is never rejected."""
    wid = _ws(conn, "SC WS2")
    _seed_players(conn, wid)
    _promote(conn, wid)
    row = conn.execute(text("SELECT runs, dismissal_type, dismissal_source_code "
                            "FROM batting_entry WHERE source_ref = '700:2'")).mappings().one()
    assert row["runs"] == 12 and row["dismissal_type"] is None and row["dismissal_source_code"] == "99"


def test_padding_rows_not_imported(conn):
    wid = _ws(conn, "SC WS3")
    _seed_players(conn, wid)
    _promote(conn, wid)
    # only the two real batters and one real bowler exist (BatsmanID/bowlerID 0 skipped)
    assert conn.execute(text("SELECT count(*) FROM batting_entry")).scalar_one() == 2
    assert conn.execute(text("SELECT count(*) FROM bowling_entry")).scalar_one() == 1


def test_scorecard_imports_even_without_people(conn):
    """Unresolved player references (no person imported) leave person_id NULL but still import the
    innings, figures and fall of wickets — unknown ≠ rejected."""
    wid = _ws(conn, "SC WS4")
    _, res = _promote(conn, wid)   # NO _seed_players
    assert res["created"]["batting_entry"] == 2 and res["created"]["fall_of_wicket"] == 1
    assert conn.execute(text("SELECT person_id FROM batting_entry WHERE source_ref = '700:1'")).scalar_one() is None
    assert conn.execute(text("SELECT runs FROM batting_entry WHERE source_ref = '700:1'")).scalar_one() == 38


def test_reimport_scorecards_no_duplicates(conn):
    wid = _ws(conn, "SC WS5")
    _seed_players(conn, wid)
    _promote(conn, wid)
    counts = {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()
              for t in ("innings", "batting_entry", "bowling_entry", "fall_of_wicket", "match")}
    # re-import the SAME payload as a new batch
    _, res2 = _promote(conn, wid)
    assert res2["created"]["innings"] == 0 and res2["matched"]["innings"] == 1
    assert res2["created"]["batting_entry"] == 0 and res2["matched"]["batting_entry"] == 2
    after = {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()
             for t in ("innings", "batting_entry", "bowling_entry", "fall_of_wicket", "match")}
    assert after == counts  # nothing duplicated


def test_rollback_removes_scorecards(conn):
    wid = _ws(conn, "SC WS6")
    _seed_players(conn, wid)
    bid, _ = _promote(conn, wid)
    out = imports.rollback_batch(conn, wid, ACTOR, bid)
    assert out["removed"]["batting_entry"] == 2 and out["removed"]["fall_of_wicket"] == 1
    assert out["removed"]["innings"] == 1 and out["removed"]["match"] == 1
    assert conn.execute(text("SELECT count(*) FROM batting_entry")).scalar_one() == 0
    assert conn.execute(text("SELECT count(*) FROM innings")).scalar_one() == 0


def test_unresolved_howout_report(conn):
    report = imports.unresolved_howout_report(PAYLOAD)
    codes = {c["code"]: c["count"] for c in report["unresolved_codes"]}
    assert codes == {"2": 1, "99": 1}                 # padding (BatsmanID 0) excluded
    assert report["total_batting_rows"] == 2
    ex = next(c for c in report["unresolved_codes"] if c["code"] == "2")["examples"][0]
    assert ex["batsman_id"] == 10 and ex["match_id"] == 500   # representative example carried
