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
from onestats.domain import imports, partnerships, people

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
            {"bowlerID": 11, "Maidens": 0, "Overs": 0.0, "Wickets": 0, "RunsA": 0, "wides": 0, "noballs": 0},  # did not bowl -> skipped
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
    assert bat["dismissal_type"] == "bowled"                            # Howout 2 -> bowled (verified legend)
    assert bat["dismissal_source_code"] == "2"                          # raw Howout preserved

    bowl = conn.execute(text("SELECT person_id, wickets, runs_conceded, maidens, wides "
                             "FROM bowling_entry WHERE source_ref = '700:20:1'")).mappings().one()
    assert bowl["wickets"] == 2 and bowl["runs_conceded"] == 30 and bowl["person_id"] == p2

    fow = conn.execute(text("SELECT wicket_number, team_score, dismissed_person_id "
                            "FROM fall_of_wicket WHERE source_ref = '700:1'")).mappings().one()
    assert fow["wicket_number"] == 1 and fow["team_score"] == 40 and fow["dismissed_person_id"] == p1


def test_imported_match_is_final_not_draft(conn):
    """An imported match is a completed historical fixture, so its lifecycle status is 'final' (not the
    'draft' a hand-authored match starts in). The scorecard approval_status stays separate (draft)."""
    wid = _ws(conn, "SC STATUS")
    _seed_players(conn, wid)
    _promote(conn, wid)
    m = conn.execute(text("SELECT status, approval_status FROM match WHERE source_ref = '500'")).mappings().one()
    assert m["status"] == "final" and m["approval_status"] == "draft"
    # a manual 'abandoned' is preserved on re-import (only a 'draft' is upgraded)
    conn.execute(text("UPDATE match SET status = 'abandoned' WHERE source_ref = '500'"))
    _promote(conn, wid)
    assert conn.execute(text("SELECT status FROM match WHERE source_ref = '500'")).scalar_one() == "abandoned"
    # a match left as 'draft' is upgraded to 'final' on re-import
    conn.execute(text("UPDATE match SET status = 'draft' WHERE source_ref = '500'"))
    _promote(conn, wid)
    assert conn.execute(text("SELECT status FROM match WHERE source_ref = '500'")).scalar_one() == "final"


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
    # only the two real batters and one real bowler exist (BatsmanID/bowlerID 0 skipped, and the
    # zero-figures "bowler" 11 who did not actually bowl is skipped)
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


def test_import_auto_generates_partnerships_from_fow(conn):
    """Partnerships are generated automatically from the imported fall of wickets — no manual button.
    Re-import does not duplicate them (the calculated partnerships are replaced, not re-added)."""
    wid = _ws(conn, "SC PART")
    _seed_players(conn, wid)
    _, res = _promote(conn, wid)
    assert res["created"]["partnership"] >= 1                 # auto-derived on import
    inn = conn.execute(text("SELECT id FROM innings WHERE source_ref = '700'")).scalar_one()
    parts = partnerships.list_partnerships(conn, inn)
    assert len(parts) >= 1
    first = next(p for p in parts if p["wicket_number"] == 1)
    assert first["origin"] == "calculated" and first["runs"] == 40   # FOW at 40 -> 1st-wicket stand

    before = conn.execute(text("SELECT count(*) FROM partnership")).scalar_one()
    _promote(conn, wid)  # re-import the same data
    assert conn.execute(text("SELECT count(*) FROM partnership")).scalar_one() == before  # no duplicates


# intra-club / same-team-both-sides match (CricketStatz listed one team id on both sides). Two
# disjoint XIs, a full two-innings card — a team can never bat against itself, so the importer gives
# the away side a distinct, flagged opponent identity instead of failing or dropping the match.
SAME_TEAM = {
    "clubs": [{"ClubID": 1, "Name": "Alpha CC"}],
    "teams": [{"TeamID": 100, "Name": "Alpha", "ClubID": 1}],   # ONLY one team in the source
    "venues": [{"GroundID": 10, "Name": "Alpha Oval"}],
    "divisions": [{"GradeID": 50, "Name": "B Grade"}],
    "matches": [{"MatchID": 900, "HomeTeam": 100, "AwayTeam": 100, "DatePlayed": "2024-02-10",
                 "Ground": 10, "Grade": 50, "Result": 1, "matchtype": 1}],
    "innings": [{"MatchID": 900, "cricket_Innings": [
        {"InningsID": 910, "InnsNumber": 1, "battingteam": 100, "bowlingteam": 100, "iresult": 1},
        {"InningsID": 920, "InnsNumber": 2, "battingteam": 100, "bowlingteam": 100, "iresult": 2},
    ]}],
    "batting": [{"MatchID": 900, "cricket_Innings": [
        {"InningsID": 910, "InnsNumber": 1, "cricket_batting": [
            {"Batpos": 1, "BatsmanID": 10, "Howout": 2, "Bowler": 30, "Fielder": 0, "Score": 40,
             "Balls": 50, "mins": 0, "sixes": 0, "fours": 5, "FOW": 0, "FOWPos": 1, "FOWBatID": 0, "FOWOvers": 0.0},
            {"Batpos": 2, "BatsmanID": 11, "Howout": 1, "Bowler": 0, "Fielder": 0, "Score": 20,
             "Balls": 30, "mins": 0, "sixes": 0, "fours": 2, "FOW": 0, "FOWPos": 2, "FOWBatID": 0, "FOWOvers": 0.0},
        ]},
        {"InningsID": 920, "InnsNumber": 2, "cricket_batting": [
            {"Batpos": 1, "BatsmanID": 30, "Howout": 2, "Bowler": 10, "Fielder": 0, "Score": 15,
             "Balls": 22, "mins": 0, "sixes": 0, "fours": 1, "FOW": 0, "FOWPos": 1, "FOWBatID": 0, "FOWOvers": 0.0},
            {"Batpos": 2, "BatsmanID": 31, "Howout": 1, "Bowler": 0, "Fielder": 0, "Score": 5,
             "Balls": 10, "mins": 0, "sixes": 0, "fours": 0, "FOW": 0, "FOWPos": 2, "FOWBatID": 0, "FOWOvers": 0.0},
        ]},
    ]}],
    "bowling": [{"MatchID": 900, "cricket_Innings": [
        {"InningsID": 910, "InnsNumber": 1, "cricket_bowling": [
            {"bowlerID": 30, "Maidens": 0, "Overs": 8.0, "Wickets": 1, "RunsA": 35, "wides": 0, "noballs": 0}]},
        {"InningsID": 920, "InnsNumber": 2, "cricket_bowling": [
            {"bowlerID": 10, "Maidens": 1, "Overs": 8.0, "Wickets": 1, "RunsA": 20, "wides": 0, "noballs": 0}]},
    ]}],
}


def test_same_team_match_splits_into_a_distinct_flagged_opponent(conn):
    """A match the source listed with the same team on both sides imports as a valid two-team fixture:
    the away side gets a distinct, flagged opponent (never auto-merged), and the two innings are split
    by parity so each has distinct batting/bowling sides — no ``teams_must_differ``, nothing dropped."""
    wid = _ws(conn, "SC INTRACLUB")
    bid = imports.parse_and_stage(conn, wid, ACTOR, payload=SAME_TEAM)["batch_id"]
    res = imports.promote_batch(conn, wid, ACTOR, bid)
    assert res["created"]["innings"] == 2            # both innings imported (no rollback / no error)
    assert res["created"]["batting_entry"] == 4

    t100 = conn.execute(text("SELECT id FROM team WHERE source_ref = '100'")).scalar_one()
    opp = conn.execute(text("SELECT id, name FROM team WHERE source_ref = '100~opp~900'")).mappings().one()
    assert opp["id"] != t100 and "opponent" in opp["name"].lower()

    # the synthetic opponent is flagged for review, never silently merged
    flagged = conn.execute(
        text("SELECT issues::text FROM import_staging_record "
             "WHERE batch_id = :b AND entity_type = 'team' AND source_ref = '100~opp~900'"),
        {"b": bid}).scalar_one()
    assert "intra_club_opponent" in flagged

    # odd innings: original side bats, opponent bowls; even innings: the reverse
    inn1 = conn.execute(text("SELECT batting_team_id, bowling_team_id FROM innings WHERE source_ref = '910'")).mappings().one()
    inn2 = conn.execute(text("SELECT batting_team_id, bowling_team_id FROM innings WHERE source_ref = '920'")).mappings().one()
    assert inn1["batting_team_id"] == t100 and inn1["bowling_team_id"] == opp["id"]
    assert inn2["batting_team_id"] == opp["id"] and inn2["bowling_team_id"] == t100

    # the match itself now has two distinct sides (home vs the opponent)
    sides = conn.execute(text("SELECT team_id, is_home FROM match_team mt "
                              "JOIN match m ON m.id = mt.match_id WHERE m.source_ref = '900'")).mappings().all()
    by_home = {s["is_home"]: s["team_id"] for s in sides}
    assert by_home[True] == t100 and by_home[False] == opp["id"]


def test_same_team_match_reimport_is_idempotent(conn):
    """Re-importing an intra-club match creates no duplicate opponent team, innings or entries."""
    wid = _ws(conn, "SC INTRACLUB2")
    bid = imports.parse_and_stage(conn, wid, ACTOR, payload=SAME_TEAM)["batch_id"]
    imports.promote_batch(conn, wid, ACTOR, bid)
    counts = {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()
              for t in ("team", "innings", "batting_entry", "bowling_entry", "match")}
    bid2 = imports.parse_and_stage(conn, wid, ACTOR, payload=SAME_TEAM)["batch_id"]
    res2 = imports.promote_batch(conn, wid, ACTOR, bid2)
    assert res2["created"]["innings"] == 0 and res2["matched"]["innings"] == 2
    after = {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()
             for t in ("team", "innings", "batting_entry", "bowling_entry", "match")}
    assert after == counts  # opponent team + scorecard not duplicated


# A player listed twice in one innings — CricketStatz sometimes emits a phantom did-not-bat row (or a
# scorer double-entry) carrying a real player id. A batter can hold only one line per innings.
DUP_BATTER = {
    "clubs": [{"ClubID": 1, "Name": "Alpha CC"}, {"ClubID": 2, "Name": "Beta CC"}],
    "teams": [{"TeamID": 100, "Name": "Alpha", "ClubID": 1}, {"TeamID": 200, "Name": "Beta", "ClubID": 2}],
    "venues": [{"GroundID": 10, "Name": "Alpha Oval"}],
    "divisions": [{"GradeID": 50, "Name": "B Grade"}],
    "matches": [{"MatchID": 901, "HomeTeam": 100, "AwayTeam": 200, "DatePlayed": "2024-03-01",
                 "Ground": 10, "Grade": 50, "Result": 1, "matchtype": 1}],
    "innings": [{"MatchID": 901, "cricket_Innings": [
        {"InningsID": 930, "InnsNumber": 1, "battingteam": 100, "bowlingteam": 200, "iresult": 1},
    ]}],
    "batting": [{"MatchID": 901, "cricket_Innings": [
        {"InningsID": 930, "InnsNumber": 1, "cricket_batting": [
            {"Batpos": 1, "BatsmanID": 10, "Howout": 2, "Bowler": 0, "Fielder": 0, "Score": 44,
             "Balls": 50, "mins": 0, "sixes": 0, "fours": 6, "FOW": 0, "FOWPos": 1, "FOWBatID": 0, "FOWOvers": 0.0},
            {"Batpos": 2, "BatsmanID": 11, "Howout": 1, "Bowler": 0, "Fielder": 0, "Score": 10,
             "Balls": 20, "mins": 0, "sixes": 0, "fours": 1, "FOW": 0, "FOWPos": 2, "FOWBatID": 0, "FOWOvers": 0.0},
            # SECOND row for BatsmanID 10 in the SAME innings (phantom / scorer double entry)
            {"Batpos": 5, "BatsmanID": 10, "Howout": 7, "Bowler": 0, "Fielder": 0, "Score": 0,
             "Balls": 0, "mins": 0, "sixes": 0, "fours": 0, "FOW": 0, "FOWPos": 5, "FOWBatID": 0, "FOWOvers": 0.0},
        ]},
    ]}],
}


def test_duplicate_batter_in_innings_keeps_first_and_flags_rest(conn):
    """A player listed twice in one innings must not abort the whole import. The importer keeps the first
    line, leaves the duplicate staged + flagged for review, and never merges or guesses."""
    wid = _ws(conn, "SC DUPBAT")
    # the duplicated player must resolve to a person for the per-innings check to apply
    people.create_person(conn, wid, ACTOR, display_name="Dup Batter", source_system=SS, source_ref="10")
    people.create_person(conn, wid, ACTOR, display_name="Other Batter", source_system=SS, source_ref="11")
    bid = imports.parse_and_stage(conn, wid, ACTOR, payload=DUP_BATTER)["batch_id"]
    res = imports.promote_batch(conn, wid, ACTOR, bid)        # must NOT raise / roll back
    assert res["created"]["batting_entry"] == 2              # player 10 (first line) + player 11
    inn = conn.execute(text("SELECT id FROM innings WHERE source_ref = '930'")).scalar_one()
    assert conn.execute(text("SELECT count(*) FROM batting_entry WHERE innings_id = :i"),
                        {"i": inn}).scalar_one() == 2
    # the kept line for player 10 is the genuine first line (Batpos 1, Score 44), not the phantom
    kept = conn.execute(text("SELECT batting_position, runs FROM batting_entry "
                             "WHERE source_ref = '930:1'")).mappings().one()
    assert (kept["batting_position"], kept["runs"]) == (1, 44)
    # the duplicate row is left staged + flagged, never promoted
    dup = conn.execute(
        text("SELECT status, issues::text AS issues FROM import_staging_record "
             "WHERE batch_id = :b AND entity_type = 'batting_entry' AND source_ref = '930:5'"),
        {"b": bid}).mappings().one()
    assert dup["status"] == "staged" and "duplicate_batter_in_innings" in dup["issues"]


# A bowler who bowls TWO spells in one innings — a scorecard shows one line per bowler (figures summed).
DUP_BOWLER = {
    "clubs": [{"ClubID": 1, "Name": "Alpha CC"}, {"ClubID": 2, "Name": "Beta CC"}],
    "teams": [{"TeamID": 100, "Name": "Alpha", "ClubID": 1}, {"TeamID": 200, "Name": "Beta", "ClubID": 2}],
    "venues": [{"GroundID": 10, "Name": "Alpha Oval"}],
    "divisions": [{"GradeID": 50, "Name": "B Grade"}],
    "matches": [{"MatchID": 902, "HomeTeam": 100, "AwayTeam": 200, "DatePlayed": "2024-03-02",
                 "Ground": 10, "Grade": 50, "Result": 1, "matchtype": 1}],
    "innings": [{"MatchID": 902, "cricket_Innings": [
        {"InningsID": 940, "InnsNumber": 1, "battingteam": 100, "bowlingteam": 200, "iresult": 1},
    ]}],
    "batting": [{"MatchID": 902, "cricket_Innings": [
        {"InningsID": 940, "InnsNumber": 1, "cricket_batting": [
            {"Batpos": 1, "BatsmanID": 10, "Howout": 2, "Bowler": 30, "Fielder": 0, "Score": 40,
             "Balls": 50, "mins": 0, "sixes": 0, "fours": 5, "FOW": 0, "FOWPos": 1, "FOWBatID": 0, "FOWOvers": 0.0},
        ]},
    ]}],
    "bowling": [{"MatchID": 902, "cricket_Innings": [
        {"InningsID": 940, "InnsNumber": 1, "cricket_bowling": [
            {"bowlerID": 30, "Maidens": 0, "Overs": 2.0, "Wickets": 0, "RunsA": 9, "wides": 0, "noballs": 0},
            {"bowlerID": 31, "Maidens": 1, "Overs": 4.0, "Wickets": 1, "RunsA": 12, "wides": 0, "noballs": 0},
            {"bowlerID": 30, "Maidens": 0, "Overs": 3.0, "Wickets": 1, "RunsA": 13, "wides": 0, "noballs": 0},  # 2nd spell
        ]},
    ]}],
}


def test_bowler_with_two_spells_combines_into_one_line(conn):
    """A bowler who bowls more than one spell in an innings is one bowling line with the figures summed
    — not two rows (which the model rejects and which rolled back the whole import). Idempotent."""
    wid = _ws(conn, "SC DUPBOWL")
    p30 = people.create_person(conn, wid, ACTOR, display_name="Spell Bowler", source_system=SS, source_ref="30")
    people.create_person(conn, wid, ACTOR, display_name="Other Bowler", source_system=SS, source_ref="31")
    bid = imports.parse_and_stage(conn, wid, ACTOR, payload=DUP_BOWLER)["batch_id"]
    imports.promote_batch(conn, wid, ACTOR, bid)   # must NOT raise / roll back
    inn = conn.execute(text("SELECT id FROM innings WHERE source_ref = '940'")).scalar_one()
    rows = conn.execute(text("SELECT person_id, overs_text, maidens, wickets, runs_conceded "
                             "FROM bowling_entry WHERE innings_id = :i"), {"i": inn}).mappings().all()
    assert len(rows) == 2                                   # one line per bowler (30 combined + 31)
    b30 = next(r for r in rows if str(r["person_id"]) == str(p30))
    assert b30["overs_text"] == "5.0"                       # 2.0 + 3.0 spells combined
    assert b30["wickets"] == 1 and b30["runs_conceded"] == 22 and b30["maidens"] == 0  # 0+1, 9+13, 0+0
    # re-import does not duplicate the bowling line
    bid2 = imports.parse_and_stage(conn, wid, ACTOR, payload=DUP_BOWLER)["batch_id"]
    imports.promote_batch(conn, wid, ACTOR, bid2)
    assert conn.execute(text("SELECT count(*) FROM bowling_entry WHERE innings_id = :i"),
                        {"i": inn}).scalar_one() == 2


def test_howout_legend_mapping():
    """The verified legend maps exactly the approved/mandated codes; everything else stays None."""
    m = imports.map_howout
    assert m(1) == "not_out" and m(2) == "bowled" and m(3) == "caught"
    assert m(4) == "caught_and_bowled" and m(5) == "caught_behind"   # c&b / caught behind
    assert m(6) == "lbw" and m(7) == "run_out" and m(8) == "stumped"
    assert m(9) == "hit_wicket" and m(10) == "obstructing" and m(12) == "hit_twice" and m(23) == "timed_out"
    assert m(0) == "dnb" and m(21) == "absent"                       # dnb/absent are non-wickets
    assert m(20) == "retired_not_out" and m(22) == "retired_out"     # retired distinction
    for c in (11, 24, 99, None, "x"):                                # still unresolved — never guessed
        assert m(c) is None


def test_remap_howout_fills_unresolved_without_overwriting(conn):
    """remap_howout_dismissals sets the type in place for verified codes that are still unresolved,
    never overwrites a type already set, never touches unmapped codes, and creates no rows."""
    wid = _ws(conn, "SC REMAP")
    _seed_players(conn, wid)
    _promote(conn, wid)
    before = conn.execute(text("SELECT count(*) FROM batting_entry")).scalar_one()
    # simulate a pre-legend import: clear the mapped type on the code-2 row
    conn.execute(text("UPDATE batting_entry SET dismissal_type = NULL WHERE source_ref = '700:1'"))
    res = imports.remap_howout_dismissals(conn, wid, ACTOR)
    assert res["by_type"].get("bowled") == 1
    assert conn.execute(text("SELECT dismissal_type FROM batting_entry WHERE source_ref = '700:1'")).scalar_one() == "bowled"
    assert "99" in res["still_unresolved"]  # the unknown code stays unresolved
    assert conn.execute(text("SELECT dismissal_type FROM batting_entry WHERE source_ref = '700:2'")).scalar_one() is None
    assert conn.execute(text("SELECT count(*) FROM batting_entry")).scalar_one() == before  # no rows created
    # idempotent: a second remap changes nothing (does not overwrite the now-set type)
    assert imports.remap_howout_dismissals(conn, wid, ACTOR)["updated"] == 0


def test_controlled_import_preview_then_commit(conn):
    """The wizard's controlled import: a preview (savepoint rolled back) persists nothing; a commit
    imports people + structural + scorecards and resolves batter references to the imported people."""
    wid = _ws(conn, "SC CTRL")
    people_payload = {"players": [
        {"PlayerID": 10, "Firstname": "Batter", "Lastname": "Ten", "DOB": "1700-01-01", "MyClub": 1},
        {"PlayerID": 20, "Firstname": "Bowler", "Lastname": "Twenty", "DOB": "1700-01-01", "MyClub": 1},
    ]}
    # PREVIEW — inside a savepoint that is rolled back (mimics the endpoint)
    sp = conn.begin_nested()
    prev = imports.controlled_import(conn, wid, ACTOR, data=PAYLOAD, people=people_payload, commit=False)
    sp.rollback()
    assert prev["committed"] is False and prev["preview"]["matches_promotable"] == 1
    assert conn.execute(text("SELECT count(*) FROM match")).scalar_one() == 0  # nothing persisted

    # COMMIT
    res = imports.controlled_import(conn, wid, ACTOR, data=PAYLOAD, people=people_payload, commit=True)
    assert res["committed"] is True
    assert res["promoted"]["created"]["match"] == 1 and res["promoted"]["created"]["batting_entry"] == 2
    assert res["people"]["promoted"]["created"]["player"] == 2
    # batter resolved to the imported person; dismissal mapped (Howout 2 -> bowled)
    bat = conn.execute(text("SELECT person_id, dismissal_type FROM batting_entry WHERE source_ref = '700:1'")).mappings().one()
    assert bat["person_id"] is not None and bat["dismissal_type"] == "bowled"
    # each imported player gains their MyClub (ClubID 1) affiliation — so selectors can scope by club
    assert res["affiliations"]["linked"] == 2
    org = conn.execute(text("SELECT id FROM organisation WHERE source_ref = '1'")).scalar_one()
    affiliated = people.list_people(conn, organisation_id=org)
    assert {p["display_name"] for p in affiliated} == {"Batter Ten", "Bowler Twenty"}  # org-scoped list
    # re-running the link creates no duplicate affiliations
    assert imports.link_cricketstatz_people_to_clubs(conn, wid, ACTOR)["linked"] == 0


def test_unresolved_howout_report(conn):
    report = imports.unresolved_howout_report(PAYLOAD)
    codes = {c["code"]: c["count"] for c in report["unresolved_codes"]}
    assert codes == {"2": 1, "99": 1}                 # padding (BatsmanID 0) excluded
    assert report["total_batting_rows"] == 2
    ex = next(c for c in report["unresolved_codes"] if c["code"] == "2")["examples"][0]
    assert ex["batsman_id"] == 10 and ex["match_id"] == 500   # representative example carried
