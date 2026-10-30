"""Automatic match results & winning margins (Phase 7, Stage 7.3).

Rolled back per test; skipped without a live DB; runs as ``onestats_app`` under FORCE RLS. Covers
win by runs, win by wickets, tie, insufficient/partial scorecards, multi-innings review, the
recorded-vs-calculated conflict warning, provenance preservation and idempotency.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import competitions, matches, results
from onestats.domain import innings as inn

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "11111111-1111-1111-1111-111111111111"


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
    wid = conn.execute(text("INSERT INTO workspace(name, type) VALUES (:n,'club') RETURNING id"), {"n": name}).scalar_one()
    set_workspace(conn, wid)
    return wid


def _team(conn, wid, name):
    org = conn.execute(text("INSERT INTO organisation(workspace_id, name, kind) VALUES (:w,:n,'club') RETURNING id"),
                       {"w": wid, "n": name + " CC"}).scalar_one()
    return conn.execute(text("INSERT INTO team(workspace_id, organisation_id, name) VALUES (:w,:o,:n) RETURNING id"),
                        {"w": wid, "o": org, "n": name}).scalar_one()


def _match(conn, wid):
    cid = competitions.create_competition(conn, wid, ACTOR, name="League")
    home, away = _team(conn, wid, "Home"), _team(conn, wid, "Away")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=cid)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    return mid, home, away


def _two_innings(conn, wid, mid, home, away, t1, t2, *, w2=10, status2="completed"):
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    i2 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=2, batting_team_id=away, bowling_team_id=home,
                            status=status2)
    inn.set_official_total(conn, wid, ACTOR, i1, total=t1, wickets=None, reason="test")
    inn.set_official_total(conn, wid, ACTOR, i2, total=t2, wickets=w2, reason="test")
    return i1, i2


def test_win_by_runs(conn):
    wid = _ws(conn, "RES RUNS")
    mid, home, away = _match(conn, wid)
    _two_innings(conn, wid, mid, home, away, 150, 120, w2=10)  # home defends, away all out
    r = results.compute_result(conn, mid)
    assert r["status"] == "sufficient" and r["result_type"] == "home_win"
    assert r["won_by_team_id"] == home and r["margin_runs"] == 30 and r["margin_wickets"] is None


def test_win_by_wickets(conn):
    wid = _ws(conn, "RES WKTS")
    mid, home, away = _match(conn, wid)
    _two_innings(conn, wid, mid, home, away, 120, 121, w2=6)  # away chases, 6 down
    r = results.compute_result(conn, mid)
    assert r["result_type"] == "away_win" and r["won_by_team_id"] == away
    assert r["margin_wickets"] == 4 and r["margin_runs"] is None


def test_tie(conn):
    wid = _ws(conn, "RES TIE")
    mid, home, away = _match(conn, wid)
    _two_innings(conn, wid, mid, home, away, 130, 130, w2=10)
    assert results.compute_result(conn, mid)["result_type"] == "tie"


def test_insufficient_when_second_innings_incomplete(conn):
    """Side batting first leads but the chase is not complete — no result is invented."""
    wid = _ws(conn, "RES PART")
    mid, home, away = _match(conn, wid)
    _two_innings(conn, wid, mid, home, away, 150, 90, w2=4, status2="in_progress")
    assert results.compute_result(conn, mid)["status"] == "insufficient"


def test_multi_innings_requires_review(conn):
    wid = _ws(conn, "RES MULTI")
    mid, home, away = _match(conn, wid)
    for n, (bt, bo) in enumerate([(home, away), (away, home), (home, away), (away, home)], start=1):
        inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=n, batting_team_id=bt, bowling_team_id=bo)
    assert results.compute_result(conn, mid)["status"] == "requires_review"


def test_multi_innings_recorded_result_gets_margin(conn):
    """A recorded two-innings-per-side result with no margin is completed from the aggregated totals:
    by wickets when the winner batted last (wickets in hand there), else by runs."""
    wid = _ws(conn, "RES MULTI MARGIN")
    mid, home, away = _match(conn, wid)
    iids = []
    for n, (bt, bo) in enumerate([(home, away), (away, home), (home, away), (away, home)], start=1):
        iids.append(inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=n, batting_team_id=bt, bowling_team_id=bo))
    for i, (tot, wk) in zip(iids, [(100, 10), (80, 10), (90, 10), (120, 2)]):
        inn.set_official_total(conn, wid, ACTOR, i, total=tot, wickets=wk, reason="t")
    # away aggregate 200 > home 190, away batted last → won by wickets (10 - 2)
    matches.set_result(conn, wid, ACTOR, mid, result_type="away_win", won_by_team_id=away, result_source="recorded")
    results.auto_apply_result(conn, wid, ACTOR, mid)
    m = matches.get_match(conn, mid)
    assert m["margin_wickets"] == 8 and m["margin_runs"] is None


def test_auto_apply_sets_calculated_and_is_idempotent(conn):
    wid = _ws(conn, "RES AUTO")
    mid, home, away = _match(conn, wid)
    _two_innings(conn, wid, mid, home, away, 150, 120, w2=10)
    out = results.auto_apply_result(conn, wid, ACTOR, mid)
    assert out["applied"] is True
    m = matches.get_match(conn, mid)
    assert m["result_type"] == "home_win" and m["margin_runs"] == 30 and m["result_source"] == "calculated"
    # idempotent: re-apply does not change the stored result
    results.auto_apply_result(conn, wid, ACTOR, mid)
    assert matches.get_match(conn, mid)["margin_runs"] == 30


def test_recorded_result_preserved_and_conflict_flagged(conn):
    wid = _ws(conn, "RES CONFLICT")
    mid, home, away = _match(conn, wid)
    _two_innings(conn, wid, mid, home, away, 150, 120, w2=10)   # scorecard => home win by 30
    # an official recorded result that disagrees (away win)
    matches.set_result(conn, wid, ACTOR, mid, result_type="away_win", won_by_team_id=away,
                       margin_runs=5, result_source="recorded")
    out = results.auto_apply_result(conn, wid, ACTOR, mid)
    assert out["applied"] is False                              # recorded result preserved
    assert matches.get_match(conn, mid)["result_type"] == "away_win"
    assert any("result_conflict" in w for w in results.result_warnings(conn, mid))  # flagged for review


def test_imported_result_with_raw_code_is_preserved(conn):
    """An imported result carrying a raw CricketStatz code is authoritative even if its provenance
    flag was not backfilled (source 'unknown') — auto-calc must not overwrite it."""
    wid = _ws(conn, "RES IMPORTED")
    mid, home, away = _match(conn, wid)
    _two_innings(conn, wid, mid, home, away, 150, 120, w2=10)   # scorecard => home win by 30
    # simulate an imported result: away_win recorded with a raw code, but source left 'unknown'
    matches.set_result(conn, wid, ACTOR, mid, result_type="away_win", won_by_team_id=away,
                       margin_runs=5, result_raw="2", result_source="unknown")
    assert results.auto_apply_result(conn, wid, ACTOR, mid)["applied"] is False  # preserved
    assert matches.get_match(conn, mid)["result_type"] == "away_win"
    assert any("result_conflict" in w for w in results.result_warnings(conn, mid))


def test_recorded_result_without_margin_gets_scorecard_margin(conn):
    """An imported/recorded result with no margin (CricketStatz gives the winner but not the margin)
    is completed from the scorecard when they agree — the recorded outcome and provenance are kept,
    only the margin is added."""
    wid = _ws(conn, "RES MARGIN BACKFILL")
    mid, home, away = _match(conn, wid)
    _two_innings(conn, wid, mid, home, away, 120, 121, w2=6)    # away chases => away win by 4 wkts
    matches.set_result(conn, wid, ACTOR, mid, result_type="away_win", won_by_team_id=away,
                       result_raw="2", result_source="recorded")   # recorded, NO margin
    out = results.auto_apply_result(conn, wid, ACTOR, mid)
    assert out["applied"] is True and out.get("margin_added") is True
    m = matches.get_match(conn, mid)
    assert m["margin_wickets"] == 4 and m["margin_runs"] is None
    assert m["result_type"] == "away_win" and m["result_source"] == "recorded" and m["result_raw"] == "2"
    # idempotent: a margin now exists, so re-applying adds nothing
    assert results.auto_apply_result(conn, wid, ACTOR, mid)["applied"] is False
    assert matches.get_match(conn, mid)["margin_wickets"] == 4


def test_recorded_win_by_runs_fills_margin_even_when_second_innings_incomplete(conn):
    """Imported innings aren't flagged complete, but a recorded result is itself the evidence the match
    finished — so a win-by-runs margin still fills from the totals (the old completion check had left it
    blank for most imported matches)."""
    wid = _ws(conn, "RES MARGIN RUNS INC")
    mid, home, away = _match(conn, wid)
    _two_innings(conn, wid, mid, home, away, 150, 120, w2=4, status2="in_progress")  # 2nd NOT complete
    assert results.compute_result(conn, mid)["status"] == "insufficient"             # calc alone: unknown
    matches.set_result(conn, wid, ACTOR, mid, result_type="home_win", won_by_team_id=home,
                       result_raw="1", result_source="recorded")
    out = results.auto_apply_result(conn, wid, ACTOR, mid)
    assert out["applied"] is True and out["margin_runs"] == 30 and out["margin_wickets"] is None
    assert matches.get_match(conn, mid)["margin_runs"] == 30


def test_margin_not_backfilled_when_scorecard_disagrees(conn):
    """The margin is only added when the scorecard agrees on the winner — a disagreement is left as a
    review conflict, never silently completed with a margin for the other side."""
    wid = _ws(conn, "RES MARGIN DISAGREE")
    mid, home, away = _match(conn, wid)
    _two_innings(conn, wid, mid, home, away, 150, 120, w2=10)   # scorecard => home win
    matches.set_result(conn, wid, ACTOR, mid, result_type="away_win", won_by_team_id=away,
                       result_raw="2", result_source="recorded")   # recorded disagrees, no margin
    assert results.auto_apply_result(conn, wid, ACTOR, mid)["applied"] is False
    m = matches.get_match(conn, mid)
    assert m["margin_runs"] is None and m["margin_wickets"] is None   # nothing invented
    assert any("result_conflict" in w for w in results.result_warnings(conn, mid))


def test_manual_result_without_margin_is_left_alone(conn):
    """A manual administrator override is never auto-completed, even if the scorecard implies a margin."""
    wid = _ws(conn, "RES MARGIN MANUAL")
    mid, home, away = _match(conn, wid)
    _two_innings(conn, wid, mid, home, away, 120, 121, w2=6)    # scorecard => away win by 4 wkts
    matches.set_result(conn, wid, ACTOR, mid, result_type="away_win", won_by_team_id=away,
                       result_source="manual")                    # manual, NO margin
    assert results.auto_apply_result(conn, wid, ACTOR, mid)["applied"] is False
    assert matches.get_match(conn, mid)["margin_wickets"] is None


def test_isolation(conn):
    wid_a = conn.execute(text("INSERT INTO workspace(name,type) VALUES ('RES ISO A','club') RETURNING id")).scalar_one()
    set_workspace(conn, wid_a)
    mid, home, away = _match(conn, wid_a)
    _two_innings(conn, wid_a, mid, home, away, 150, 120, w2=10)
    wid_b = conn.execute(text("INSERT INTO workspace(name,type) VALUES ('RES ISO B','club') RETURNING id")).scalar_one()
    set_workspace(conn, wid_b)
    with pytest.raises(ValueError, match="match_not_found"):
        results.compute_result(conn, mid)   # not visible from another workspace
