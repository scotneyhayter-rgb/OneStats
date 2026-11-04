"""Cricsheet parser — accurate, era-safe aggregation from ball-by-ball JSON. Pure, no database.

A small hand-built men's Test innings exercises the rules that matter for an accurate scorecard:
boundaries, a leg-bye and a wide (charged / faced correctly), a maiden over, a bowler-credited catch
vs a non-credited run-out, a declaration, and fall-of-wickets. Expected figures are computed by hand in
the comments so a regression is obvious.
"""
from __future__ import annotations

import datetime as dt

import pytest

from onestats.domain.intl import cricsheet


def _delivery(batter, bowler, batter_runs, *, extras=None, wicket=None):
    total = batter_runs + sum((extras or {}).values())
    d = {"batter": batter, "bowler": bowler, "non_striker": "NS",
         "runs": {"batter": batter_runs, "extras": sum((extras or {}).values()), "total": total}}
    if extras:
        d["extras"] = extras
    if wicket:
        d["wickets"] = [wicket]
    return d


DOC = {
    "meta": {"data_version": "1.1.0"},
    "info": {
        "match_type": "Test", "gender": "male", "balls_per_over": 6,
        "dates": ["2024-01-10", "2024-01-11"], "teams": ["Australia", "England"],
        "venue": "MCG", "city": "Melbourne", "event": {"name": "The Ashes", "match_number": 2},
        "toss": {"winner": "Australia", "decision": "bat"},
        "outcome": {"winner": "Australia", "by": {"runs": 100}},
        "players": {"Australia": ["D Warner", "S Smith", "T Head"], "England": ["J Anderson", "S Broad", "J Root", "B Stokes"]},
        "registry": {"people": {"D Warner": "aa11", "S Smith": "bb22", "S Broad": "cc33"}},
    },
    "innings": [
        {
            "team": "Australia", "declared": True,
            "overs": [
                # Over 0 — Anderson, a maiden: six dot balls to Warner (0 runs conceded)
                {"over": 0, "deliveries": [_delivery("D Warner", "J Anderson", 0) for _ in range(6)]},
                # Over 1 — Broad: four, six, a leg-bye (not charged), a wide (not faced/charged legal),
                # Warner caught (credits Broad), then Smith on strike
                {"over": 1, "deliveries": [
                    _delivery("D Warner", "S Broad", 4),
                    _delivery("D Warner", "S Broad", 6),
                    _delivery("D Warner", "S Broad", 0, extras={"legbyes": 2}),
                    _delivery("D Warner", "S Broad", 0, extras={"wides": 1}),
                    _delivery("D Warner", "S Broad", 0,
                              wicket={"player_out": "D Warner", "kind": "caught", "fielders": [{"name": "J Root"}]}),
                    _delivery("S Smith", "S Broad", 1),
                    _delivery("S Smith", "S Broad", 0),
                ]},
                # Over 2 — Anderson: Smith run out (NOT the bowler's wicket), then Head scores 3
                {"over": 2, "deliveries": [
                    _delivery("S Smith", "J Anderson", 0),
                    _delivery("S Smith", "J Anderson", 0,
                              wicket={"player_out": "S Smith", "kind": "run out", "fielders": [{"name": "B Stokes"}]}),
                    _delivery("T Head", "J Anderson", 3),
                    _delivery("T Head", "J Anderson", 0),
                    _delivery("T Head", "J Anderson", 0),
                    _delivery("T Head", "J Anderson", 0),
                ]},
            ],
        }
    ],
}


@pytest.fixture
def match():
    return cricsheet.parse_match(DOC, source_ref="123456")


def test_match_metadata(match):
    assert match.format == "test" and match.gender == "male" and match.balls_per_over == 6
    assert match.start_date == dt.date(2024, 1, 10)
    assert match.teams == ["Australia", "England"] and match.venue == "MCG"
    assert match.match_number == 2 and match.event_name == "The Ashes"
    assert match.registry["D Warner"] == "aa11"       # stable cross-source id carried through
    assert match.source_ref == "123456"


def test_batting_is_accurate(match):
    inns = match.innings[0]
    assert inns.declared is True
    bat = {b.name: b for b in inns.batting}
    w = bat["D Warner"]
    assert w.runs == 10 and w.fours == 1 and w.sixes == 1   # 0(o0) + 4+6 (o1)
    assert w.balls_faced == 10                               # 6 (o0) + d1,d2,d3(leg-bye faced),d5 (o1); wide NOT faced
    assert w.out is True and w.dismissal_kind == "caught" and w.bowler == "S Broad"
    assert w.fielders == ["J Root"]
    assert bat["S Smith"].out is True and bat["S Smith"].dismissal_kind == "run out"
    assert bat["S Smith"].bowler is None                     # run-out credits no bowler
    assert bat["T Head"].out is False and bat["T Head"].runs == 3   # not out


def test_bowling_charges_and_maidens_are_accurate(match):
    bowl = {b.name: b for b in match.innings[0].bowling}
    # Broad: bat runs 4+6+1 = 11, plus 1 wide = 12; the leg-bye is NOT charged. 1 wicket (the catch).
    assert bowl["S Broad"].runs_conceded == 12 and bowl["S Broad"].wickets == 1
    assert bowl["S Broad"].legal_balls == 6 and bowl["S Broad"].wides == 1
    # Anderson: over 0 maiden (0 runs) + over 2 (3 runs). 12 legal balls, 0 wickets (run-out not his).
    assert bowl["J Anderson"].runs_conceded == 3 and bowl["J Anderson"].wickets == 0
    assert bowl["J Anderson"].maidens == 1 and bowl["J Anderson"].legal_balls == 12


def test_innings_totals_and_fall(match):
    inns = match.innings[0]
    assert inns.total_runs == 17 and inns.total_wickets == 2     # 0 + 14 + 3 ; two wickets
    assert inns.legal_balls == 18
    assert inns.extras == {"legbyes": 2, "wides": 1}
    assert [(f.wicket_number, f.player_out, f.team_runs) for f in inns.fall_of_wickets] == [
        (1, "D Warner", 13), (2, "S Smith", 14),
    ]


def test_rejects_non_mens_international():
    with pytest.raises(ValueError):
        cricsheet.parse_match({"info": {"match_type": "T20", "gender": "female"}}, source_ref="x")
    with pytest.raises(ValueError):
        cricsheet.parse_match({"info": {"match_type": "ODM", "gender": "male"}}, source_ref="x")  # domestic
