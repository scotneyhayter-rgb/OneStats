"""International match-index register (Part C) — DB-backed.

Rolled back per test; skipped without a live DB. Covers duplicate prevention by shared source-ref,
multi-source reconciliation, official-status import gating, the expected-count honesty rule (>= 2
sources, unknown stays NULL not zero), genuine recomputed coverage, and workspace isolation.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.intl import match_index as mi

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
    wid = conn.execute(text("INSERT INTO workspace(name, type) VALUES (:n,'international') RETURNING id"),
                       {"n": name}).scalar_one()
    conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a, :u) ON CONFLICT (id) DO NOTHING"),
                 {"a": ACTOR, "u": f"actor-{name}"})
    set_workspace(conn, wid)
    return wid


def _match(conn, wid, fmt="test"):
    return conn.execute(text("INSERT INTO match(workspace_id, format) VALUES (:w, :f) RETURNING id"),
                        {"w": wid, "f": fmt}).scalar_one()


def test_register_expected_vs_indexed_state(conn):
    wid = _ws(conn, "IDX STATE")
    bare = mi.register(conn, wid, ACTOR, format="test", source_refs={"espncricinfo": "62395"})
    assert bare["state"] == "expected"
    detailed = mi.register(conn, wid, ACTOR, format="odi", source_refs={"espncricinfo": "64001"},
                           team_a="Australia", team_b="England", start_date="1971-01-05")
    assert detailed["state"] == "indexed"


def test_duplicate_prevented_by_shared_source_ref(conn):
    wid = _ws(conn, "IDX DEDUPE")
    first = mi.register(conn, wid, ACTOR, format="test", source_refs={"espncricinfo": "62395"})
    # re-discovery via the SAME espncricinfo id reconciles to the same row, adding the wikipedia ref
    again = mi.register(conn, wid, ACTOR, format="test",
                        source_refs={"espncricinfo": "62395", "wikipedia": "First_Test_1877"})
    assert again["id"] == first["id"]
    assert again["source_refs"] == {"espncricinfo": "62395", "wikipedia": "First_Test_1877"}
    assert conn.execute(text("SELECT count(*) FROM match_index_entry WHERE workspace_id = :w"),
                        {"w": wid}).scalar_one() == 1


def test_existing_values_not_silently_overwritten(conn):
    wid = _ws(conn, "IDX NOOVERWRITE")
    mi.register(conn, wid, ACTOR, format="test", source_refs={"espncricinfo": "1"}, team_a="Australia")
    merged = mi.register(conn, wid, ACTOR, format="test", source_refs={"espncricinfo": "1"}, team_a="Aus")
    assert merged["team_a"] == "Australia"  # first value preserved; corrections go via approval


def test_import_gated_by_official_status(conn):
    wid = _ws(conn, "IDX GATE")
    cand = mi.register(conn, wid, ACTOR, format="t20i", source_refs={"espncricinfo": "9"},
                       official_status="candidate")
    mid = _match(conn, wid, "t20i")
    with pytest.raises(ValueError, match="not_recognised_cannot_import"):
        mi.link_match(conn, wid, ACTOR, cand["id"], mid)
    # once recognised, it imports and advances state
    mi.set_official_status(conn, wid, ACTOR, cand["id"], "recognised")
    linked = mi.link_match(conn, wid, ACTOR, cand["id"], mid)
    assert linked["state"] == "imported" and str(linked["match_id"]) == str(mid)
    verified = mi.mark_verified(conn, wid, ACTOR, cand["id"])
    assert verified["state"] == "verified" and verified["verified_at"] is not None


def test_mark_verified_requires_import(conn):
    wid = _ws(conn, "IDX VERIFY GUARD")
    e = mi.register(conn, wid, ACTOR, format="test", source_refs={"espncricinfo": "2"})
    with pytest.raises(ValueError, match="cannot_verify_unimported"):
        mi.mark_verified(conn, wid, ACTOR, e["id"])


def test_expected_count_requires_multiple_sources(conn):
    wid = _ws(conn, "IDX EXPECTED")
    with pytest.raises(ValueError, match="expected_requires_multiple_sources"):
        mi.set_expected(conn, wid, ACTOR, "test", "all", expected_count=2360,
                        sources={"espncricinfo": 2360})
    cov = mi.set_expected(conn, wid, ACTOR, "test", "all", expected_count=2360,
                          sources={"espncricinfo": 2360, "wikipedia": 2360})
    assert cov["expected_count"] == 2360 and cov["coverage_state"] == "reconciled"


def test_coverage_counts_are_genuine_and_unknown_is_not_zero(conn):
    wid = _ws(conn, "IDX COVERAGE")
    mi.register(conn, wid, ACTOR, format="test", source_refs={"espncricinfo": "a"})
    mi.register(conn, wid, ACTOR, format="test", source_refs={"espncricinfo": "b"})
    cov = mi.recount_coverage(conn, wid, "test", "all")
    assert cov["indexed_count"] == 2 and cov["imported_count"] == 0
    # expected stays NULL (unknown) until reconciliation — never defaulted to zero
    assert cov["expected_count"] is None
    summ = mi.summary(conn, wid)
    assert summ["test"]["expected"] is None  # unknown, NOT 0
    assert summ["test"]["states"]["expected"] == 2
    assert summ["odi"]["states"]["expected"] == 0  # a real zero: no odi rows indexed


def test_candidate_and_disputed_excluded_from_recognised_counts(conn):
    wid = _ws(conn, "IDX STATUS COUNTS")
    mi.register(conn, wid, ACTOR, format="t20i", source_refs={"x": "1"})
    mi.register(conn, wid, ACTOR, format="t20i", source_refs={"x": "2"}, official_status="candidate")
    mi.register(conn, wid, ACTOR, format="t20i", source_refs={"x": "3"}, official_status="disputed")
    summ = mi.summary(conn, wid)["t20i"]
    assert summ["states"]["expected"] == 1 and summ["candidates"] == 1 and summ["disputed"] == 1


def test_workspace_isolation(conn):
    wid_a = _ws(conn, "IDX ISO A")
    mi.register(conn, wid_a, ACTOR, format="test", source_refs={"espncricinfo": "100"})
    wid_b = _ws(conn, "IDX ISO B")  # GUC now points at B
    assert mi.find_by_source_ref(conn, wid_b, "espncricinfo", "100") is None
    summ_b = mi.summary(conn, wid_b)
    assert summ_b["test"]["states"]["expected"] == 0
