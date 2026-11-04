"""Phase 8, Stage 8.2 — the CricketStatz adapter maps a CS export into the Canonical model.

Pure logic (no database). Confirms detection, parsing, and a faithful CS→CCDM normalisation that
preserves provenance, captains/keepers (incl. both-roles), the toss winner (home/away code, decision
unknown), raw+mapped dismissal codes, fall of wickets, and unknown-is-not-zero. Reuses the verified
HOWOUT/result legends, so the adapter cannot drift from the existing importer.
"""
from __future__ import annotations

import json

from onestats.domain.importing import detect_adapter, registry
from onestats.domain.importing.adapters.cricket_statz import CricketStatzAdapter

# a small, realistic CricketStatz slice: home player 10 is BOTH captain and keeper; away cap 20/keeper 21;
# toss won by home (code 1); dismissals use a verified (2=bowled) code and an unresolved-but-preserved
# code (11 = "handled the ball" — documented in CS_HOWOUT as having no 1:1 OneStats type).
PAYLOAD = {
    "clubs": [{"ClubID": 1, "Name": "Alpha CC"}],
    "teams": [{"TeamID": 100, "Name": "Alpha 1st", "ClubID": 1}, {"TeamID": 200, "Name": "Beta 1st", "ClubID": 1}],
    "venues": [{"GroundID": 10, "Name": "Alpha Oval"}],
    "divisions": [{"GradeID": 50, "Name": "B Grade"}],
    "players": [{"PlayerID": p, "Firstname": f"P{p}", "Lastname": "X", "DOB": "1990-01-01", "MyClub": 1}
                for p in (10, 11, 20, 21)],
    "matches": [{"MatchID": 500, "HomeTeam": 100, "AwayTeam": 200, "DatePlayed": "2024-01-06T00:00:00",
                 "Ground": 10, "Grade": 50, "Result": 1, "round": "1", "matchtype": 1,
                 "homecaptain1": 10, "homekeeper1": 10, "homekeeper2": 0,
                 "awaycaptain1": 20, "awaykeeper1": 21, "awaykeeper2": 0, "tosswonby": 1}],
    "innings": [{"MatchID": 500, "cricket_Innings": [
        {"InningsID": 700, "InnsNumber": 1, "battingteam": 100, "bowlingteam": 200,
         "Byes": 4, "Legbyes": 2, "Noballs": 1, "Wides": 3}]}],
    "batting": [{"MatchID": 500, "cricket_Innings": [
        {"InningsID": 700, "InnsNumber": 1, "cricket_batting": [
            {"Batpos": 1, "BatsmanID": 10, "Howout": 2, "Bowler": 20, "Fielder": 0, "Score": 38, "Balls": 41,
             "mins": 60, "sixes": 1, "fours": 5, "FOW": 40, "FOWPos": 1, "FOWBatID": 10, "FOWOvers": 12.3},
            {"Batpos": 2, "BatsmanID": 11, "Howout": 11, "Bowler": 20, "Fielder": 21, "Score": 0, "Balls": None,
             "FOW": 60, "FOWPos": 2, "FOWBatID": 11, "FOWOvers": 18.0}]}]}],
    "bowling": [{"MatchID": 500, "cricket_Innings": [
        {"InningsID": 700, "InnsNumber": 1, "cricket_bowling": [
            {"bowlerID": 20, "Maidens": 1, "Overs": 8.0, "Wickets": 2, "RunsA": 30, "wides": 1, "noballs": 0}]}]}],
}


def test_detect_recognises_cricket_statz_and_rejects_others():
    a = CricketStatzAdapter()
    assert a.detect(json.dumps(PAYLOAD)) > 0.8
    assert a.detect('{"some":"other","rows":[1,2,3]}') == 0.0
    assert a.detect(json.dumps(PAYLOAD).encode("utf-8-sig")) > 0.8   # bytes / BOM tolerated


def test_registered_in_global_registry():
    assert registry.get("cricket_statz").format_id == "cricket_statz"
    assert detect_adapter(json.dumps(PAYLOAD)).format_id == "cricket_statz"


def test_normalize_structural_and_people():
    ds = CricketStatzAdapter().normalize(PAYLOAD)
    assert ds.provenance.source_system == "cricket_statz"
    assert ds.validate_provenance() == []
    assert {t.source_ref for t in ds.teams} == {"100", "200"}
    assert ds.teams[0].club_ref == "1"
    p10 = next(p for p in ds.people if p.source_ref == "10")
    assert p10.display_name == "P10 X" and p10.club_ref == "1" and p10.dob_precision == "exact"


def test_normalize_match_roles_toss_and_result():
    m = CricketStatzAdapter().normalize(PAYLOAD).matches[0]
    assert m.source_ref == "500" and m.home_team_ref == "100" and m.away_team_ref == "200"
    assert str(m.match_date) == "2024-01-06" and m.match_format == "1 innings per side"
    assert m.result_code == "1" and m.result_type == "home_win" and m.result_status == "known"
    # home player 10 is BOTH captain and keeper; keeper2 absent (0 → None, not invented)
    assert m.home_captain_ref == "10" and m.home_keeper_ref == "10" and m.home_keeper2_ref is None
    assert m.away_captain_ref == "20" and m.away_keeper_ref == "21"
    assert m.toss_won_by == "home"          # code 1 → home; decision not in source, left unknown


def test_normalize_scorecard_dismissals_fow_and_unknown_not_zero():
    inn = CricketStatzAdapter().normalize(PAYLOAD).matches[0].innings[0]
    assert inn.batting_team_ref == "100" and inn.byes == 4 and inn.wides == 3
    b1, b2 = inn.batting
    # verified code mapped; raw code always preserved
    assert b1.dismissal_source_code == "2" and b1.dismissal_type == "bowled"
    # unresolved code: raw kept, mapped type left None (never guessed)
    assert b2.dismissal_source_code == "11" and b2.dismissal_type is None
    # unknown is not zero: b2 faced an unknown number of balls, scored a real 0
    assert b2.runs == 0 and b2.balls_faced is None
    assert len(inn.fall_of_wickets) == 2 and inn.fall_of_wickets[0].team_score == 40
    assert inn.bowling[0].wickets == 2 and inn.bowling[0].runs_conceded == 30


def test_parse_handles_bytes_and_bom():
    a = CricketStatzAdapter()
    assert a.parse(json.dumps(PAYLOAD).encode("utf-8-sig"))["matches"][0]["MatchID"] == 500
