"""player_analysis pure-function tests (no database)."""
from __future__ import annotations

from onestats.domain.records import player_analysis as pa


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
