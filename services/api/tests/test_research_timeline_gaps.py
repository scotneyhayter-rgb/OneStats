"""Phase 10, Stages 10.12/10.13 — research timeline (season coverage) + gaps.

The timeline computes honest metrics (never claims 'comprehensive' from counts; a season with no known
matches is 'unassessed'); an explicit assessment can raise a season to 'comprehensive'. Gaps are derived
from real data. Rolled back; skipped without a live DB.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import matches
from onestats.domain.research import gaps, timeline

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
    conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a, :u) ON CONFLICT (id) DO NOTHING"),
                 {"a": ACTOR, "u": f"actor-{name}"})
    set_workspace(conn, wid)
    return wid


def _comp(conn, wid):
    return conn.execute(text("INSERT INTO competition(workspace_id, name) VALUES (:w, 'ADCA') RETURNING id"),
                        {"w": wid}).scalar_one()


def _season(conn, wid, comp, label):
    return conn.execute(
        text("INSERT INTO season(workspace_id, competition_id, label, start_date) VALUES (:w,:c,:l,:d) RETURNING id"),
        {"w": wid, "c": comp, "l": label, "d": dt.date(1897, 10, 1)}).scalar_one()


def test_classify_computed_never_comprehensive():
    assert timeline.classify_computed(0, 0) == "unassessed"
    assert timeline.classify_computed(5, 0) == "significant_gaps"
    assert timeline.classify_computed(5, 5) == "partial"   # all known verified, but still only 'partial'


def test_timeline_metrics_and_assessment_override(conn):
    wid = _ws(conn, "TL")
    comp = _comp(conn, wid)
    s = _season(conn, wid, comp, "1897/98")
    m1 = matches.create_match(conn, wid, ACTOR, competition_id=comp, season_id=s)
    matches.set_approval(conn, wid, ACTOR, m1, status="approved")
    matches.create_match(conn, wid, ACTOR, competition_id=comp, season_id=s)  # a draft, no result

    tl = timeline.season_timeline(conn, wid, competition_id=comp)
    row = next(x for x in tl["seasons"] if x["season_id"] == str(s))
    assert row["total_matches"] == 2 and row["verified_matches"] == 1
    assert row["coverage_class"] == "partial"             # computed, capped
    assert "methodology" in tl

    # an explicit, evidence-backed assessment raises it to comprehensive
    timeline.set_assessment(conn, wid, ACTOR, season_id=s, assessed_class="comprehensive",
                            basis="Full ADCA fixture list cross-checked")
    tl2 = timeline.season_timeline(conn, wid, competition_id=comp)
    row2 = next(x for x in tl2["seasons"] if x["season_id"] == str(s))
    assert row2["coverage_class"] == "comprehensive" and row2["assessment_basis"].startswith("Full ADCA")


def test_gaps_from_real_data(conn):
    wid = _ws(conn, "GAPS")
    matches.create_match(conn, wid, ACTOR)                       # no result, no date, no scorecard, draft
    g = gaps.coverage_gaps(conn, wid)
    assert g["matches_without_result"]["count"] == 1
    assert g["matches_unknown_date"]["count"] == 1
    assert g["matches_missing_scorecard"]["count"] == 1
    assert g["draft_scorecards"]["count"] == 1
    assert len(g["matches_without_result"]["sample"]) == 1
