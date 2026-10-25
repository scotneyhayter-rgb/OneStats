"""Phase 10, Stage 10.1 — Research Centre foundation.

Research projects + Source Library CRUD, source→match linking, duplicate-source detection, a real
database-backed dashboard, and workspace isolation (FORCE RLS). Rolled back; skipped without a live DB.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.research import dashboard, projects, sources

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


def _match(conn, wid):
    return conn.execute(text("INSERT INTO match(workspace_id) VALUES (:w) RETURNING id"), {"w": wid}).scalar_one()


def test_project_crud(conn):
    wid = _ws(conn, "RC PROJ")
    p = projects.create_project(conn, wid, ACTOR, title="RMCC 1891-1900",
                                scope={"club": "Rhymney", "from": "1891", "to": "1900"})
    assert p["status"] == "active" and p["title"] == "RMCC 1891-1900"
    assert projects.get_project(conn, p["id"])["scope"]["club"] == "Rhymney"
    projects.update_project(conn, wid, ACTOR, p["id"], status="paused", owner="scotney")
    updated = projects.get_project(conn, p["id"])
    assert updated["status"] == "paused" and updated["owner"] == "scotney"
    assert len(projects.list_projects(conn, wid)) == 1
    assert len(projects.list_projects(conn, wid, status="active")) == 0


def test_project_requires_title_and_valid_status(conn):
    wid = _ws(conn, "RC PROJ VAL")
    with pytest.raises(ValueError, match="title_required"):
        projects.create_project(conn, wid, ACTOR, title="   ")
    with pytest.raises(ValueError, match="invalid_status"):
        projects.create_project(conn, wid, ACTOR, title="x", status="bogus")


def test_source_metadata_and_pubdate_separate(conn):
    wid = _ws(conn, "RC SRC")
    s = sources.create_source(
        conn, wid, ACTOR, title="The Ararat Advertiser, 6 Nov 1931", source_type="newspaper_article",
        publication="Ararat Advertiser", publication_date=dt.date(1931, 11, 6),
        publication_date_precision="exact", page_ref="p.3", copyright_status="public_domain",
        file_sha256="abc123")
    assert s["publication"] == "Ararat Advertiser"
    assert str(s["publication_date"]) == "1931-11-06"      # publication date preserved, distinct from match date
    assert s["ocr_status"] == "none"
    assert len(sources.list_sources(conn, wid)) == 1


def test_source_type_and_precision_validated(conn):
    wid = _ws(conn, "RC SRC VAL")
    with pytest.raises(ValueError, match="invalid_source_type"):
        sources.create_source(conn, wid, ACTOR, title="x", source_type="tweet")
    with pytest.raises(ValueError, match="invalid_date_precision"):
        sources.create_source(conn, wid, ACTOR, title="x", source_type="pdf", publication_date_precision="guess")


def test_duplicate_source_detected_by_hash(conn):
    wid = _ws(conn, "RC DUP")
    sources.create_source(conn, wid, ACTOR, title="scan A", source_type="image", file_sha256="deadbeef")
    dup = sources.find_duplicate_by_hash(conn, wid, "deadbeef")
    assert dup is not None and dup["title"] == "scan A"
    assert sources.find_duplicate_by_hash(conn, wid, "nothere") is None


def test_source_links_to_one_canonical_match(conn):
    wid = _ws(conn, "RC LINK")
    mid = _match(conn, wid)
    s1 = sources.create_source(conn, wid, ACTOR, title="Monday report", source_type="newspaper_article")
    s2 = sources.create_source(conn, wid, ACTOR, title="Tuesday edition", source_type="newspaper_edition")
    sources.link_match(conn, wid, ACTOR, s1["id"], mid, role="primary")
    sources.link_match(conn, wid, ACTOR, s2["id"], mid, role="supporting")
    linked = sources.list_sources_for_match(conn, wid, mid)
    assert {r["title"] for r in linked} == {"Monday report", "Tuesday edition"}
    # idempotent: re-linking the same source/match does not duplicate
    sources.link_match(conn, wid, ACTOR, s1["id"], mid)
    assert len(sources.list_sources_for_match(conn, wid, mid)) == 2


def test_dashboard_uses_real_db_counts(conn):
    wid = _ws(conn, "RC DASH")
    d0 = dashboard.dashboard_summary(conn, wid)
    assert d0["projects_total"] == 0 and d0["sources_total"] == 0 and d0["matches_under_investigation"] == 0
    projects.create_project(conn, wid, ACTOR, title="proj")
    s = sources.create_source(conn, wid, ACTOR, title="src", source_type="pdf")
    mid = _match(conn, wid)   # a draft match
    sources.link_match(conn, wid, ACTOR, s["id"], mid)
    d1 = dashboard.dashboard_summary(conn, wid)
    assert d1["projects_total"] == 1 and d1["projects_active"] == 1
    assert d1["sources_total"] == 1 and len(d1["sources_recent"]) == 1
    assert d1["matches_under_investigation"] == 1
    assert d1["draft_scorecards"] == 1 and d1["verified"] == 0
    assert d1["disputed"] == 0 and d1["conflicting_evidence"] == 0


def test_workspace_isolation(conn):
    wa = _ws(conn, "RC ISO A")
    projects.create_project(conn, wa, ACTOR, title="A-only project")
    sources.create_source(conn, wa, ACTOR, title="A-only source", source_type="pdf")
    wb = _ws(conn, "RC ISO B")   # switches the workspace GUC to B
    assert projects.list_projects(conn, wb) == []
    assert sources.list_sources(conn, wb) == []
    assert dashboard.dashboard_summary(conn, wb)["projects_total"] == 0
