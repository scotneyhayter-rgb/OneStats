"""Finding classification vs existing matches — pure/offline. Verifies the review buckets and the
cautious never-merge behaviour (name-only, capped confidence, unknown stays unknown)."""
from __future__ import annotations

from onestats.domain.research import classify

# A small in-memory match index: one Rhymney v Moyston match in 1905.
INDEX = [
    {"match_id": "m1", "year": 1905, "teams": [{"rhymney"}, {"moyston"}]},
    {"match_id": "m2", "year": 1950, "teams": [{"horsham"}, {"ararat"}]},
]


def _ex(teams, dates=None):
    return {"observed_teams": teams, "observed_dates": dates}


def test_possible_duplicate_same_teams_and_year():
    v = classify.classify(_ex(["Rhymney CC", "Moyston Cricket Club"], ["14 January 1905"]), INDEX)
    assert v["classification"] == "possible_duplicate"
    assert v["candidate_match_ids"] == ["m1"]
    assert 0 < v["confidence"] <= 0.9


def test_possible_duplicate_same_teams_no_date():
    v = classify.classify(_ex(["Rhymney", "Moyston"]), INDEX)
    assert v["classification"] == "possible_duplicate"
    assert v["confidence"] <= 0.9


def test_additional_evidence_one_known_team():
    v = classify.classify(_ex(["Rhymney", "Pleasant Creek"], ["1905"]), INDEX)
    assert v["classification"] == "additional_evidence"


def test_new_when_teams_absent_from_workspace():
    v = classify.classify(_ex(["Stawell", "Great Western"], ["1905"]), INDEX)
    assert v["classification"] == "new"
    assert v["candidate_match_ids"] == []


def test_unknown_without_team_names():
    v = classify.classify(_ex([], ["1905"]), INDEX)
    assert v["classification"] == "unknown"
    assert v["confidence"] is None


def test_conflicting_when_result_margin_differs():
    idx = [{"match_id": "m1", "year": 1905, "teams": [{"rhymney"}, {"moyston"}],
            "margin_runs": 20, "margin_wickets": None}]
    ex = {"observed_teams": ["Rhymney", "Moyston"], "observed_dates": ["1905"],
          "observed_result": {"outcome": "win", "margin": 14, "unit": "runs", "text": "won by 14 runs"}}
    v = classify.classify(ex, idx)
    assert v["classification"] == "conflicting"
    assert "14 runs" in v["reason"] and "20 runs" in v["reason"]


def test_no_conflict_when_result_agrees():
    idx = [{"match_id": "m1", "year": 1905, "teams": [{"rhymney"}, {"moyston"}],
            "margin_runs": 14, "margin_wickets": None}]
    ex = {"observed_teams": ["Rhymney", "Moyston"], "observed_dates": ["1905"],
          "observed_result": {"outcome": "win", "margin": 14, "unit": "runs", "text": "won by 14 runs"}}
    assert classify.classify(ex, idx)["classification"] == "possible_duplicate"


def test_club_suffixes_do_not_block_match():
    # "Rhymney Cricket Club 1st XI" must still match the recorded "rhymney" token set.
    v = classify.classify(_ex(["Rhymney Cricket Club 1st XI", "Moyston CC"]), INDEX)
    assert v["classification"] == "possible_duplicate"
