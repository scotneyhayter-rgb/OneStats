"""Phase 10, Stage 10.9/10.10 — field-level provenance + conflict handling.

Multiple sources contribute claims to one match; conflicts are detected (both claims retained);
accepting one claim supersedes competing ones without deleting them; rejected claims are kept.
Rolled back; skipped without a live DB.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.research import provenance, sources

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


def _src(conn, wid, title):
    return sources.create_source(conn, wid, ACTOR, title=title, source_type="newspaper_article")["id"]


def test_claims_from_many_sources_build_one_match(conn):
    wid = _ws(conn, "PV BUILD")
    mid = _match(conn, wid)
    sa_, sb = _src(conn, wid, "Mon paper"), _src(conn, wid, "scorebook")
    provenance.record_claim(conn, wid, ACTOR, match_id=mid, field_path="match.result",
                            source_id=sa_, claimed_value="Rhymney won by 5 wkts", normalised_value="home_win")
    provenance.record_claim(conn, wid, ACTOR, match_id=mid, field_path="batting.home.Smith.runs",
                            source_id=sb, claimed_value="54", normalised_value="54")
    rows = provenance.list_for_match(conn, wid, mid)
    assert {r["field_path"] for r in rows} == {"match.result", "batting.home.Smith.runs"}


def test_unknown_is_preserved_not_zero(conn):
    wid = _ws(conn, "PV UNKNOWN")
    mid = _match(conn, wid)
    s = _src(conn, wid, "faded clipping")
    c = provenance.record_claim(conn, wid, ACTOR, match_id=mid, field_path="bowling.away.Jones.wickets",
                                source_id=s, claimed_value="illegible", normalised_value=None)
    assert c["normalised_value"] is None   # unknown stays unknown, never coerced to 0


def test_conflict_detected_and_both_claims_retained(conn):
    wid = _ws(conn, "PV CONFLICT")
    mid = _match(conn, wid)
    sa_, sb = _src(conn, wid, "paper A"), _src(conn, wid, "paper B")
    a = provenance.record_claim(conn, wid, ACTOR, match_id=mid, field_path="batting.home.Smith.runs",
                                source_id=sa_, claimed_value="54", normalised_value="54")
    provenance.record_claim(conn, wid, ACTOR, match_id=mid, field_path="batting.home.Smith.runs",
                            source_id=sb, claimed_value="45", normalised_value="45")
    conflicts = provenance.field_conflicts(conn, wid, mid)
    assert len(conflicts) == 1 and conflicts[0]["field_path"] == "batting.home.Smith.runs"
    assert len(conflicts[0]["claims"]) == 2   # both retained, side by side

    # accept one -> the other is superseded (kept), conflict resolved, history preserved
    provenance.accept_claim(conn, wid, ACTOR, a["id"], note="scorebook agrees")
    assert provenance.field_conflicts(conn, wid, mid) == []
    statuses = {r["source_id"]: r["status"] for r in provenance.list_for_field(conn, wid, mid, "batting.home.Smith.runs")}
    assert statuses[sa_] == "accepted" and statuses[sb] == "superseded"   # loser retained, not deleted


def test_reject_is_retained(conn):
    wid = _ws(conn, "PV REJECT")
    mid = _match(conn, wid)
    s = _src(conn, wid, "dubious source")
    c = provenance.record_claim(conn, wid, ACTOR, match_id=mid, field_path="match.date",
                                source_id=s, claimed_value="1931-02-30", normalised_value="1931-02-30")
    provenance.reject_claim(conn, wid, ACTOR, c["id"], note="impossible date")
    kept = provenance.list_for_field(conn, wid, mid, "match.date")
    assert len(kept) == 1 and kept[0]["status"] == "rejected" and kept[0]["decision_note"] == "impossible date"


def test_resubmitting_a_source_claim_updates_in_place(conn):
    wid = _ws(conn, "PV UPSERT")
    mid = _match(conn, wid)
    s = _src(conn, wid, "paper")
    provenance.record_claim(conn, wid, ACTOR, match_id=mid, field_path="match.result",
                            source_id=s, claimed_value="draw", normalised_value="draw")
    provenance.record_claim(conn, wid, ACTOR, match_id=mid, field_path="match.result",
                            source_id=s, claimed_value="tie", normalised_value="tie")
    rows = provenance.list_for_field(conn, wid, mid, "match.result")
    assert len(rows) == 1 and rows[0]["normalised_value"] == "tie"   # one claim per source, updated
