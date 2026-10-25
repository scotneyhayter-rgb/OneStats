"""Phase 8, Stage 8.5 — duplicate detection + multiple sources per match (R1).

Rolled back per test; skipped without a live DB. Confirms confidence-based duplicate detection
(exact by source id / full fixture match, possible by partial), and that a second source attaches to
a match as additional evidence with conflicting fields surfaced for review — never overwriting it.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import competitions, match_sources, matches
from onestats.domain.importing import dedupe

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


def _team(conn, wid, name):
    org = conn.execute(text("INSERT INTO organisation(workspace_id,name,kind) VALUES (:w,:n,'club') RETURNING id"),
                       {"w": wid, "n": name + " CC"}).scalar_one()
    return conn.execute(text("INSERT INTO team(workspace_id,organisation_id,name) VALUES (:w,:o,:n) RETURNING id"),
                        {"w": wid, "o": org, "n": name}).scalar_one()


def _match(conn, wid, *, d, home, away, grade=None, venue=None, source_ref="X1"):
    cid = competitions.create_competition(conn, wid, ACTOR, name="League")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=cid, grade_id=grade, venue_id=venue,
                               match_date=d, source_system="cricket_statz", source_ref=source_ref)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    return mid


def test_duplicate_detection_exact_and_possible(conn):
    wid = _ws(conn, "DEDUPE")
    home, away = _team(conn, wid, "Alpha"), _team(conn, wid, "Beta")
    venue = conn.execute(text("INSERT INTO venue(workspace_id,name) VALUES (:w,'Oval') RETURNING id"), {"w": wid}).scalar_one()
    mid = _match(conn, wid, d=date(2024, 1, 6), home=home, away=away, venue=venue, source_ref="CS-500")

    # exact by source identifier
    hits = dedupe.find_match_duplicates(conn, wid, source_system="cricket_statz", source_ref="CS-500",
                                        match_date=date(2024, 1, 6), home_team_id=home, away_team_id=away)
    assert hits[0]["match_id"] == str(mid) and hits[0]["kind"] == "exact" and hits[0]["confidence"] == 1.0

    # a different source (no matching id): date + both teams + venue → exact-confidence fixture match
    hits = dedupe.find_match_duplicates(conn, wid, source_system="news_archive", source_ref="NA-1",
                                        match_date=date(2024, 1, 6), home_team_id=home, away_team_id=away, venue_id=venue)
    assert hits and hits[0]["match_id"] == str(mid)
    assert any("same venue" in r for r in hits[0]["reasons"])

    # date + teams only (no grade/venue given) → a POSSIBLE match, not exact (never auto-merged)
    hits = dedupe.find_match_duplicates(conn, wid, source_system="news_archive", source_ref="NA-2",
                                        match_date=date(2024, 1, 6), home_team_id=home, away_team_id=away)
    assert hits[0]["kind"] == "possible" and hits[0]["confidence"] == 0.7

    # a different date → no candidate
    assert dedupe.find_match_duplicates(conn, wid, source_system="news_archive", source_ref="NA-3",
                                        match_date=date(2024, 2, 1), home_team_id=home, away_team_id=away) == []


def test_attach_multiple_sources_and_surface_conflicts(conn):
    wid = _ws(conn, "R1 SOURCES")
    home, away = _team(conn, wid, "Alpha"), _team(conn, wid, "Beta")
    mid = _match(conn, wid, d=date(2024, 1, 6), home=home, away=away, source_ref="CS-500")

    # the CricketStatz source, then a newspaper edition that disagrees on the result
    a = match_sources.attach_source(conn, wid, ACTOR, mid, source_system="cricket_statz", source_ref="CS-500",
                                    recorded_fields={"result_label": "home_win", "home_total": 150})
    b = match_sources.attach_source(conn, wid, ACTOR, mid, source_system="news_archive", source_ref="HERALD-1",
                                    recorded_fields={"result_label": "tie", "home_total": 150}, edition="Herald, 7 Jan")
    assert a["created"] is True and b["created"] is True
    assert len(match_sources.list_match_sources(conn, mid)) == 2

    # the match itself is untouched by attaching sources (no overwrite)
    assert matches.get_match(conn, mid)["result_type"] in (None, "unknown")

    # the result disagreement is surfaced for review; the agreed field is not a conflict
    conflicts = match_sources.source_conflicts(conn, mid)
    fields = {c["field"] for c in conflicts}
    assert "result_label" in fields and "home_total" not in fields

    # idempotent: re-attaching the same source updates in place, not a duplicate
    again = match_sources.attach_source(conn, wid, ACTOR, mid, source_system="news_archive", source_ref="HERALD-1",
                                        recorded_fields={"result_label": "tie"})
    assert again["created"] is False
    assert len(match_sources.list_match_sources(conn, mid)) == 2
