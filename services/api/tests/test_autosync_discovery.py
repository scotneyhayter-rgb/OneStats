"""Phase 9, Stages 9.4-9.9 — AutoSync discovery.

Rolled back per test; skipped without a live DB. Covers new-match discovery + classification, the
review queue and acceptance (import as draft), authorised auto-import+approval, updated-scorecard
detection that never overwrites an approved scorecard, bulk review, coverage recording, and that a
source failure is recorded as health/failed-coverage, never as 'searched, no matches'.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import match_sources, matches
from onestats.domain.autosync import discovery, sources
from onestats.domain.autosync.connectors import FixtureConnector
from onestats.domain.importing import pipeline
from onestats.domain.importing.sync import AUTHORISED_AUTOMATIC, REVIEW_REQUIRED

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "11111111-1111-1111-1111-111111111111"

ROWS = [
    {"Date": "2024-01-06", "HomeTeam": "Alpha CC", "AwayTeam": "Beta CC", "Result": "Home win"},
    {"Date": "2024-01-13", "HomeTeam": "Gamma CC", "AwayTeam": "Delta CC", "Result": "Away win"},
]


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


def _conn_feed(rows=ROWS, system="news_feed", updated=None):
    return FixtureConnector(system, rows, updated_rows=updated)


def test_discover_new_queues_and_records_coverage(conn):
    wid = _ws(conn, "DISC NEW")
    out = discovery.discover_new(conn, wid, ACTOR, connector=_conn_feed(), mode=REVIEW_REQUIRED, scope_key="season:2023/24")
    assert out["status"] == "ok" and out["counts"]["new"] == 2 and out["queued"] == 2 and out["auto_imported"] == 0
    assert len(discovery.list_items(conn, wid, status="pending_review")) == 2
    # nothing imported in review mode
    assert conn.execute(text("SELECT count(*) FROM match WHERE source_system='news_feed'")).scalar_one() == 0
    cov = discovery.list_coverage(conn, wid)
    assert cov and cov[0]["status"] == "searched" and cov[0]["matches_found"] == 2


def test_accept_item_imports_as_draft(conn):
    wid = _ws(conn, "DISC ACCEPT")
    discovery.discover_new(conn, wid, ACTOR, connector=_conn_feed(), mode=REVIEW_REQUIRED)
    item = discovery.list_items(conn, wid)[0]
    accepted = discovery.accept_item(conn, wid, ACTOR, item["id"])
    assert accepted["status"] == "accepted" and accepted["match_id"] is not None
    assert matches.get_match(conn, accepted["match_id"])["approval_status"] == "draft"   # never auto-approved


def test_authorised_mode_auto_imports_and_approves(conn):
    wid = _ws(conn, "DISC AUTO")
    out = discovery.discover_new(conn, wid, ACTOR, connector=_conn_feed(), mode=AUTHORISED_AUTOMATIC, can_approve=True)
    assert out["auto_imported"] == 2
    mids = conn.execute(text("SELECT id FROM match WHERE source_system='news_feed'")).scalars().all()
    assert len(mids) == 2
    assert all(matches.get_match(conn, m)["approval_status"] == "approved" for m in mids)


def test_authorised_without_permission_queues_only(conn):
    wid = _ws(conn, "DISC AUTO NOPERM")
    out = discovery.discover_new(conn, wid, ACTOR, connector=_conn_feed(), mode=AUTHORISED_AUTOMATIC, can_approve=False)
    assert out["auto_imported"] == 0 and out["queued"] == 2


def test_classification_existing_and_additional_evidence(conn):
    wid = _ws(conn, "DISC CLASS")
    # import a match first (from CSV), then discover the SAME fixture from a different source
    a = FixtureConnector("csv_feed", [ROWS[0]])
    ds = a.fetch_new(None).dataset
    pipeline.import_dataset(conn, wid, ACTOR, dataset=ds, commit=True)

    # same source id again -> existing
    same = discovery.discover_new(conn, wid, ACTOR, connector=FixtureConnector("csv_feed", [ROWS[0]]), mode=REVIEW_REQUIRED)
    assert same["counts"].get("existing") == 1
    # different source, same date + teams -> POSSIBLE duplicate (queued for review, never auto-merged)
    other = discovery.discover_new(conn, wid, ACTOR, connector=FixtureConnector("herald", [ROWS[0]]), mode=REVIEW_REQUIRED)
    assert other["counts"].get("possible_duplicate") == 1
    item = next(i for i in discovery.list_items(conn, wid) if i["source_system"] == "herald")
    assert item["classification"] == "possible_duplicate" and item["match_id"] is not None   # links the candidate


def test_discover_updated_queues_change_without_overwriting_approved(conn):
    wid = _ws(conn, "DISC UPDATED")
    discovery.discover_new(conn, wid, ACTOR, connector=_conn_feed([ROWS[0]]), mode=AUTHORISED_AUTOMATIC, can_approve=True)
    mid = conn.execute(text("SELECT id FROM match WHERE source_system='news_feed'")).scalar_one()
    assert matches.get_match(conn, mid)["approval_status"] == "approved"
    before_result = matches.get_match(conn, mid)["result_type"]

    # the source now reports a different result for the same match
    changed_row = {**ROWS[0], "Result": "Tie"}
    out = discovery.discover_updated(conn, wid, ACTOR, connector=_conn_feed(ROWS, updated=[changed_row]))
    assert out["changed"] == 1
    item = next(i for i in discovery.list_items(conn, wid) if i["kind"] == "updated_scorecard")
    pc = item["proposed_changes"] or {}
    # only the genuine change is flagged (the result), not every field
    assert item["classification"] == "conflicting" and "result_label" in pc
    assert pc["result_label"]["was"] == "home_win" and pc["result_label"]["now"] == "tie"
    # the approved scorecard is UNCHANGED — the change only sits in the review queue
    assert matches.get_match(conn, mid)["result_type"] == before_result


def test_accepting_possible_duplicate_attaches_source_not_new_match(conn):
    wid = _ws(conn, "DISC ATTACH")
    pipeline.import_dataset(conn, wid, ACTOR, dataset=FixtureConnector("csv_feed", [ROWS[0]]).fetch_new(None).dataset, commit=True)
    before = conn.execute(text("SELECT count(*) FROM match")).scalar_one()
    # a different source reports the same fixture with a different result
    discovery.discover_new(conn, wid, ACTOR, connector=FixtureConnector("herald", [{**ROWS[0], "Result": "Tie"}]), mode=REVIEW_REQUIRED)
    item = next(i for i in discovery.list_items(conn, wid) if i["source_system"] == "herald")
    assert item["classification"] == "possible_duplicate" and item["match_id"] is not None

    accepted = discovery.accept_item(conn, wid, ACTOR, item["id"])
    assert accepted["status"] == "accepted"
    # NO duplicate match; the existing match gains a second source (R1), with the result conflict kept
    assert conn.execute(text("SELECT count(*) FROM match")).scalar_one() == before
    assert len(match_sources.list_match_sources(conn, accepted["match_id"])) == 2
    conflicts = {c["field"] for c in match_sources.source_conflicts(conn, accepted["match_id"])}
    assert "result_label" in conflicts


def test_rediscovery_does_not_reopen_accepted_or_duplicate(conn):
    wid = _ws(conn, "DISC REDISCOVER")
    discovery.discover_new(conn, wid, ACTOR, connector=_conn_feed(), mode=REVIEW_REQUIRED)
    item = discovery.list_items(conn, wid)[0]
    discovery.accept_item(conn, wid, ACTOR, item["id"])     # one accepted -> draft match exists
    matches_before = conn.execute(text("SELECT count(*) FROM match WHERE source_system='news_feed'")).scalar_one()

    # re-run discovery: the accepted match is now 'existing' (not re-queued), no duplicate match
    out = discovery.discover_new(conn, wid, ACTOR, connector=_conn_feed(), mode=REVIEW_REQUIRED)
    assert out["counts"].get("existing") == 1
    assert discovery.get_item(conn, item["id"])["status"] == "accepted"   # NOT reopened
    assert conn.execute(text("SELECT count(*) FROM match WHERE source_system='news_feed'")).scalar_one() == matches_before
    # the other (un-accepted) item is still pending, not duplicated
    assert len([i for i in discovery.list_items(conn, wid) if i["status"] == "pending_review"]) == 1


def test_bulk_review_accepts_many(conn):
    wid = _ws(conn, "DISC BULK")
    discovery.discover_new(conn, wid, ACTOR, connector=_conn_feed(), mode=REVIEW_REQUIRED)
    ids = [i["id"] for i in discovery.list_items(conn, wid)]
    out = discovery.bulk_review(conn, wid, ACTOR, ids, action="accept")
    assert out["count"] == 2
    assert conn.execute(text("SELECT count(*) FROM match WHERE source_system='news_feed'")).scalar_one() == 2


def test_source_failure_is_health_not_empty_result(conn):
    wid = _ws(conn, "DISC FAIL")
    src = sources.register_source(conn, wid, ACTOR, connector_id="news_feed", name="News Feed")

    class Boom:
        source_system = "news_feed"
        def fetch_new(self, since):
            raise RuntimeError("source outage")

    out = discovery.discover_new(conn, wid, ACTOR, connector=Boom(), source_id=src["id"],
                                 mode=REVIEW_REQUIRED, scope_key="season:2023/24")
    assert out["status"] == "failed"
    # recorded as FAILED coverage + source health 'down' — never 'searched, no matches'
    cov = discovery.list_coverage(conn, wid)
    assert cov and cov[0]["status"] == "failed"
    assert sources.get_source(conn, src["id"])["reliability"] == "down"
