"""player_analysis pure-function tests (no database)."""
from __future__ import annotations

import uuid
from datetime import date

from onestats.domain.records import player_analysis as pa


def test_org_clause_adds_a_club_filter_only_when_an_organisation_is_given():
    """The club filter is opt-in: no organisation → no SQL and no bound param (whole career); an
    organisation → a filter on the given innings-side column plus a single :org parameter."""
    params: dict = {}
    assert pa._org_clause("i.batting_team_id", None, params) == ""
    assert params == {}
    oid = uuid.uuid4()
    clause = pa._org_clause("i.bowling_team_id", oid, params)
    assert "i.bowling_team_id IN (SELECT id FROM team WHERE organisation_id = :org)" in clause
    assert params == {"org": oid}


def test_bowl_agg_handles_tied_best_figures():
    """Two innings tying on wickets AND runs must not crash the best-figures pick. ``max()`` previously
    carried the row dict as a tie-breaker and fell through to comparing dicts (unorderable)."""
    rows = [
        {"match_id": "m1", "balls": 24, "runs": 20, "wickets": 2, "maidens": 1},
        {"match_id": "m2", "balls": 24, "runs": 20, "wickets": 2, "maidens": 0},
    ]
    agg = pa._bowl_agg(rows)
    assert agg["best"] == "2-20"
    assert agg["wickets"] == 4 and agg["matches"] == 2


def test_bowl_agg_best_is_most_wickets_then_fewest_runs():
    rows = [
        {"match_id": "m1", "balls": 30, "runs": 10, "wickets": 3, "maidens": 1},
        {"match_id": "m2", "balls": 30, "runs": 5, "wickets": 3, "maidens": 2},   # same wickets, fewer runs
        {"match_id": "m3", "balls": 30, "runs": 2, "wickets": 2, "maidens": 0},
    ]
    assert pa._bowl_agg(rows)["best"] == "3-5"


def test_spells_orders_oldest_first_and_buckets_wickets():
    """Bowling spells feed the Charts tab: innings oldest-first, and a 0..5+ wickets-per-innings frequency.
    Innings with no recorded wickets (None) are excluded; a 6-for folds into the 5+ bucket."""
    rows = [
        {"match_date": date(2020, 3, 1), "wickets": 2, "runs": 30},
        {"match_date": date(2019, 1, 1), "wickets": 6, "runs": 40},   # earlier → sorts first
        {"match_date": date(2021, 2, 1), "wickets": 0, "runs": 25},
        {"match_date": date(2022, 2, 1), "wickets": None, "runs": None},  # not a counted spell
    ]
    out = pa._spells(rows)
    assert [i["date"] for i in out["innings"]] == ["2019-01-01", "2020-03-01", "2021-02-01"]
    assert out["innings"][0]["wickets"] == 6
    freq = {b["range"]: b["count"] for b in out["frequency"]}
    assert freq == {"0": 1, "1": 0, "2": 1, "3": 0, "4": 0, "5+": 1}
