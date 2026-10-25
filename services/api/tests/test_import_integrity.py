"""Import integrity — end-to-end preservation check (Phase 7, Stage 7.9).

Imports a synthetic CricketStatz-shaped scorecard through the controlled importer and verifies that
every piece of source information is preserved or correctly derived: source identifiers/provenance
on all entities, dismissal source codes, fall of wickets, auto-derived partnerships, the result,
club affiliations, and that an approved imported match feeds the official-statistics ledger. Rolled
back; skipped without a live DB. Nothing is invented and re-import creates no duplicates.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import imports, matches, recalc

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "11111111-1111-1111-1111-111111111111"

PAYLOAD = {
    "clubs": [{"ClubID": 1, "Name": "Alpha CC"}],
    "teams": [{"TeamID": 100, "Name": "Alpha 1st", "ClubID": 1}, {"TeamID": 200, "Name": "Beta 1st", "ClubID": 1}],
    "venues": [{"GroundID": 10, "Name": "Alpha Oval"}],
    "divisions": [{"GradeID": 50, "Name": "B Grade"}],
    "matches": [{"MatchID": 500, "HomeTeam": 100, "AwayTeam": 200, "DatePlayed": "2024-01-06",
                 "Ground": 10, "Grade": 50, "Result": 1, "round": "1", "matchtype": 1}],
    "innings": [{"MatchID": 500, "cricket_Innings": [
        {"InningsID": 700, "InnsNumber": 1, "battingteam": 100, "bowlingteam": 200, "iresult": 1,
         "Byes": 4, "Legbyes": 2, "Noballs": 1, "Wides": 3}]}],
    "batting": [{"MatchID": 500, "cricket_Innings": [
        {"InningsID": 700, "InnsNumber": 1, "cricket_batting": [
            {"Batpos": 1, "BatsmanID": 10, "Howout": 2, "Bowler": 20, "Fielder": 0, "Score": 38, "Balls": 41,
             "mins": 60, "sixes": 1, "fours": 5, "FOW": 40, "FOWPos": 1, "FOWBatID": 10, "FOWOvers": 12.3},
            {"Batpos": 2, "BatsmanID": 11, "Howout": 3, "Bowler": 20, "Fielder": 21, "Score": 12, "Balls": 20,
             "mins": 0, "sixes": 0, "fours": 1, "FOW": 60, "FOWPos": 2, "FOWBatID": 11, "FOWOvers": 18.0}]}]}],
    "bowling": [{"MatchID": 500, "cricket_Innings": [
        {"InningsID": 700, "InnsNumber": 1, "cricket_bowling": [
            {"bowlerID": 20, "Maidens": 1, "Overs": 8.0, "Wickets": 2, "RunsA": 30, "wides": 1, "noballs": 0}]}]}],
}
PEOPLE = {"players": [{"PlayerID": p, "Firstname": f"P{p}", "Lastname": "X", "DOB": "1700-01-01", "MyClub": 1}
                     for p in (10, 11, 20, 21)]}


def _ws(conn, name):
    wid = conn.execute(text("INSERT INTO workspace(name, type) VALUES (:n,'club') RETURNING id"), {"n": name}).scalar_one()
    conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a, :u) ON CONFLICT (id) DO NOTHING"),
                 {"a": ACTOR, "u": f"actor-{name}"})
    set_workspace(conn, wid)
    return wid


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


def test_import_preserves_everything_and_feeds_official_stats(conn):
    wid = _ws(conn, "INTEGRITY")
    res = imports.controlled_import(conn, wid, ACTOR, data=PAYLOAD, people=PEOPLE, commit=True)
    assert res["committed"] is True

    # provenance: source_ref preserved on every entity type
    for table, ref in [("match", "500"), ("team", "100"), ("venue", "10"), ("innings", "700"),
                       ("batting_entry", "700:1"), ("bowling_entry", "700:20:1"), ("fall_of_wicket", "700:1")]:
        got = conn.execute(text(f"SELECT source_system FROM {table} WHERE source_ref = :r"), {"r": ref}).scalar_one_or_none()
        assert got == "cricket_statz", f"{table} lost its source provenance"

    mid = conn.execute(text("SELECT id FROM match WHERE source_ref = '500'")).scalar_one()
    # dismissal source codes preserved (and mapped via the verified legend)
    bat = conn.execute(text("SELECT dismissal_type, dismissal_source_code FROM batting_entry WHERE source_ref='700:1'")).mappings().one()
    assert bat["dismissal_source_code"] == "2" and bat["dismissal_type"] == "bowled"
    # fall of wickets imported; partnerships auto-derived; extras preserved
    iid = conn.execute(text("SELECT id FROM innings WHERE source_ref='700'")).scalar_one()
    assert conn.execute(text("SELECT count(*) FROM fall_of_wicket WHERE innings_id=:i"), {"i": iid}).scalar_one() == 2
    assert conn.execute(text("SELECT count(*) FROM partnership WHERE innings_id=:i AND origin='calculated'"), {"i": iid}).scalar_one() >= 1
    assert conn.execute(text("SELECT byes FROM innings WHERE id=:i"), {"i": iid}).scalar_one() == 4
    # result preserved (recorded CricketStatz code 1 = home win), format left separate/untouched
    m = matches.get_match(conn, mid)
    assert m["result_type"] == "home_win" and m["result_source"] == "recorded"
    # imported players carry their MyClub affiliation
    assert res["affiliations"]["linked"] == 4

    # imported matches are NOT auto-approved -> no official stats yet
    assert m["approval_status"] == "draft"
    p10 = conn.execute(text("SELECT person_id FROM person_source_identity WHERE source_ref='10'")).scalar_one()
    assert recalc.official_player_batting(conn, wid, p10)["runs"] == 0
    # approve -> official statistics appear from the ledger (bulk approval of historical imports)
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    assert recalc.official_player_batting(conn, wid, p10)["runs"] == 38

    # re-import the same data creates no duplicate matches/entries
    before = {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()
              for t in ("match", "innings", "batting_entry", "bowling_entry", "fall_of_wicket")}
    imports.controlled_import(conn, wid, ACTOR, data=PAYLOAD, people=PEOPLE, commit=True)
    after = {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()
             for t in ("match", "innings", "batting_entry", "bowling_entry", "fall_of_wicket")}
    assert after == before
