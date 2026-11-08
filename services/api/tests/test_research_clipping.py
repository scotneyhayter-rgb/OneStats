"""Scorecard-clipping parser (Stage 10.17). Pure unit tests — no DB.

The parser must be conservative and honest: it extracts a draft only, leaves genuinely unknown figures
blank (never zero), keeps the raw line, and never guesses a player's identity. These tests lock that in.
"""
from __future__ import annotations

from onestats.domain.research import clipping


def _by_name(batters, name):
    return next(b for b in batters if b.name == name)


def test_parses_a_typical_batting_block():
    text = """
J Smith c Jones b Brown 42
A Allen lbw b Brown 7
P Hayter not out 15
R Carey run out 3
B Davies b Williams 0
Extras (b 4, lb 2, w 1) 7
Total (all out, 48.2 overs) 210
""".strip()
    parsed = clipping.parse_clipping(text)
    names = [b.name for b in parsed.batters]
    assert names == ["J Smith", "A Allen", "P Hayter", "R Carey", "B Davies"]

    smith = _by_name(parsed.batters, "J Smith")
    assert smith.dismissal_kind == "caught"
    assert smith.fielder_name == "Jones"
    assert smith.bowler_name == "Brown"
    assert smith.runs == 42

    allen = _by_name(parsed.batters, "A Allen")
    assert allen.dismissal_kind == "lbw"
    assert allen.bowler_name == "Brown"
    assert allen.runs == 7

    hayter = _by_name(parsed.batters, "P Hayter")
    assert hayter.dismissal_kind == "not_out"
    assert hayter.bowler_name is None
    assert hayter.fielder_name is None
    assert hayter.runs == 15

    carey = _by_name(parsed.batters, "R Carey")
    assert carey.dismissal_kind == "run_out"
    assert carey.bowler_name is None

    davies = _by_name(parsed.batters, "B Davies")
    assert davies.dismissal_kind == "bowled"
    assert davies.bowler_name == "Williams"
    assert davies.runs == 0  # a genuinely read 0 is a 0

    # Positions are the reading order within the innings.
    assert [b.position for b in parsed.batters] == [1, 2, 3, 4, 5]


def test_unknown_score_stays_blank_not_zero():
    # The score was cut off the clipping — runs must be unknown (None), never defaulted to 0.
    parsed = clipping.parse_clipping("P Hayter not out")
    assert len(parsed.batters) == 1
    assert parsed.batters[0].name == "P Hayter"
    assert parsed.batters[0].runs is None
    assert parsed.batters[0].dismissal_kind == "not_out"


def test_caught_and_bowled_and_stumped():
    parsed = clipping.parse_clipping("M Waugh c & b Warne 88\nG Jones st Healy b Warne 12")
    cb = _by_name(parsed.batters, "M Waugh")
    assert cb.dismissal_kind == "caught_and_bowled"
    assert cb.bowler_name == "Warne"
    st = _by_name(parsed.batters, "G Jones")
    assert st.dismissal_kind == "stumped"
    assert st.fielder_name == "Healy"
    assert st.bowler_name == "Warne"


def test_balls_faced_in_parentheses():
    parsed = clipping.parse_clipping("S Hayter not out 42 (63)")
    b = parsed.batters[0]
    assert b.runs == 42
    assert b.balls == 63


def test_bowling_analysis_is_parsed_and_separated():
    text = "Bowling\nBrown 10-2-35-4\nWilliams 9.2-1-28-3"
    parsed = clipping.parse_clipping(text)
    assert [b.name for b in parsed.batters] == []
    assert [b.name for b in parsed.bowlers] == ["Brown", "Williams"]
    brown = parsed.bowlers[0]
    assert brown.overs_text == "10"
    assert brown.maidens == 2
    assert brown.runs_conceded == 35
    assert brown.wickets == 4
    williams = parsed.bowlers[1]
    assert williams.overs_text == "9.2"
    assert williams.wickets == 3


def test_totals_and_summaries_are_not_treated_as_players():
    text = "Extras (b 4, lb 2) 6\nTotal (all out) 210\nFall of wickets: 1-10, 2-40\nDid not bat: X, Y"
    parsed = clipping.parse_clipping(text)
    assert parsed.batters == []
    assert len(parsed.unparsed_lines) == 4


def test_names_keep_initials_but_drop_stray_punctuation():
    parsed = clipping.parse_clipping("J.P. O'Brien-Smith b Brown* 10")
    b = parsed.batters[0]
    assert b.name == "J.P. O'Brien-Smith"
    assert b.bowler_name == "Brown"
    assert b.runs == 10


def test_raw_line_is_preserved_for_every_row():
    parsed = clipping.parse_clipping("J Smith c Jones b Brown 42")
    assert parsed.batters[0].raw == "J Smith c Jones b Brown 42"


def test_empty_text_is_empty_result():
    parsed = clipping.parse_clipping("")
    assert parsed.batters == []
    assert parsed.bowlers == []
    assert parsed.unparsed_lines == []


def test_to_dict_shape_and_disclaimer():
    d = clipping.parse_clipping("J Smith b Brown 1").to_dict()
    assert set(d) == {"batters", "bowlers", "unparsed_lines", "disclaimer"}
    assert "confirm" in d["disclaimer"].lower()
    assert d["batters"][0]["name"] == "J Smith"
