"""Phase 10, Stages 10.7/10.8 — historical scorecard reconstruction + multiple sources, one match.

Reuses the Phase 6 match model and Phase 7 approval; a reconstruction starts as a draft holding only
what is known, accepts many sources into one canonical match, and reports its state. Rolled back;
skipped without a live DB.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.research import provenance, reconstruction, sources

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


def _src(conn, wid, title):
    return sources.create_source(conn, wid, ACTOR, title=title, source_type="newspaper_article")["id"]


def test_start_provisional_match_with_unknown_date(conn):
    wid = _ws(conn, "RC START")
    m = reconstruction.start_reconstruction(conn, wid, ACTOR, date_precision="season", notes="RMCC 1897 vs Pomonal")
    assert m["approval_status"] == "draft"        # reuses Phase 7 approval
    assert m["match_date"] is None                # unknown date preserved, not fabricated
    assert m["date_precision"] == "season"


def test_date_range_precision_is_retained(conn):
    wid = _ws(conn, "RC RANGE")
    m = reconstruction.start_reconstruction(conn, wid, ACTOR, match_date=dt.date(1897, 1, 2),
                                            match_date_end=dt.date(1897, 1, 9), date_precision="range")
    assert m["date_precision"] == "range"
    assert str(m["match_date"]) == "1897-01-02" and str(m["match_date_end"]) == "1897-01-09"


def test_four_sources_build_one_canonical_match(conn):
    wid = _ws(conn, "RC MULTI")
    s_mon = _src(conn, wid, "Monday paper (result + 1st innings)")
    m = reconstruction.start_reconstruction(conn, wid, ACTOR, source_id=s_mon)
    mid = m["id"]
    for title, role in [("Tuesday edition (batting)", "supporting"),
                        ("Later article (captain/keeper)", "supporting"),
                        ("Surviving scorebook (bowling)", "corroborating")]:
        reconstruction.attach_source(conn, wid, ACTOR, mid, _src(conn, wid, title), role=role)
    # record claims from several sources against the ONE match
    provenance.record_claim(conn, wid, ACTOR, match_id=mid, field_path="match.result", source_id=s_mon,
                            claimed_value="Rhymney won", normalised_value="home_win")
    summ = reconstruction.summary(conn, wid, mid)
    assert summ["sources"] == 4          # four sources, one canonical match (no duplicates)
    assert summ["provenance_fields"] == 1
    assert summ["conflicts"] == 0
    assert len(summ["source_list"]) == 4


def test_summary_reports_conflicts(conn):
    wid = _ws(conn, "RC SUMM")
    a, b = _src(conn, wid, "paper A"), _src(conn, wid, "paper B")
    m = reconstruction.start_reconstruction(conn, wid, ACTOR, source_id=a)
    mid = m["id"]
    reconstruction.attach_source(conn, wid, ACTOR, mid, b)
    provenance.record_claim(conn, wid, ACTOR, match_id=mid, field_path="batting.home.Smith.runs",
                            source_id=a, claimed_value="54", normalised_value="54")
    provenance.record_claim(conn, wid, ACTOR, match_id=mid, field_path="batting.home.Smith.runs",
                            source_id=b, claimed_value="45", normalised_value="45")
    assert reconstruction.summary(conn, wid, mid)["conflicts"] == 1
