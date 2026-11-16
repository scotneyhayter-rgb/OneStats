"""Read-only scorecard assembly — pure-function tests (no database) for the dismissal notation and the
result line."""
from __future__ import annotations

from onestats.domain.records import scorecard as sc

NAMES = {"b1": "J Bowler", "f1": "A Fielder"}


def _r(dt, bowler=None, fielder=None):
    return {"dismissal_type": dt, "bowler_person_id": bowler, "fielder_person_id": fielder}


def test_dismissal_notation_is_standard():
    assert sc._how_out(_r("bowled", "b1"), NAMES) == "b J Bowler"
    assert sc._how_out(_r("caught", "b1", "f1"), NAMES) == "c A Fielder b J Bowler"
    assert sc._how_out(_r("caught_and_bowled", "b1"), NAMES) == "c & b J Bowler"
    assert sc._how_out(_r("lbw", "b1"), NAMES) == "lbw b J Bowler"
    assert sc._how_out(_r("stumped", "b1", "f1"), NAMES) == "st A Fielder b J Bowler"
    assert sc._how_out(_r("run_out", None, "f1"), NAMES) == "run out (A Fielder)"
    assert sc._how_out(_r("run_out"), NAMES) == "run out"
    assert sc._how_out(_r("not_out"), NAMES) == "not out"
    assert sc._how_out(_r("dnb"), NAMES) == "did not bat"
    assert sc._how_out(_r("bowled"), NAMES) == "b ?"      # missing bowler is '?', never invented
    assert sc._how_out(_r(None), NAMES) == ""              # no dismissal recorded


def test_result_text_mirrors_the_app():
    teams = {"t1": "Alpha", "t2": "Beta"}
    assert sc._result_text({"result_type": "home_win", "won_by_team_id": "t1", "margin_runs": 25}, teams) == "Alpha won by 25 runs"
    assert sc._result_text({"result_type": "away_win", "won_by_team_id": "t2", "margin_wickets": 1}, teams) == "Beta won by 1 wicket"
    assert sc._result_text({"result_type": "home_win", "won_by_team_id": "t1"}, teams) == "Alpha won"
    assert sc._result_text({"result_type": "tie"}, teams) == "Match tied"
    assert sc._result_text({"result_type": "draw"}, teams) == "Match drawn"
    assert sc._result_text({"result_type": "unknown"}, teams) is None
    assert sc._result_text({}, teams) is None
