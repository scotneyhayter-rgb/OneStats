"""Phase 8, Stage 8.9 — Phase 9 AutoSync service interfaces.

The orchestrator reuses the manual importer's services: it imports as draft and only approves +
recalculates in authorised-automatic mode with the approver permission. A fake source shows the
SyncSource contract is usable. Rolled back; the pure protocol checks need no DB.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import matches
from onestats.domain.importing import sync
from onestats.domain.importing.model import (
    CanonicalClub,
    CanonicalDataset,
    CanonicalMatch,
    CanonicalTeam,
    SourceProvenance,
)

settings = get_settings()
ACTOR = "11111111-1111-1111-1111-111111111111"


def _dataset(ref="s1") -> CanonicalDataset:
    ds = CanonicalDataset(provenance=SourceProvenance(source_system="online_feed"))
    ds.clubs = [CanonicalClub(source_ref="alpha", name="Alpha"), CanonicalClub(source_ref="beta", name="Beta")]
    ds.teams = [CanonicalTeam(source_ref="alpha", name="Alpha", club_ref="alpha"),
                CanonicalTeam(source_ref="beta", name="Beta", club_ref="beta")]
    ds.matches = [CanonicalMatch(source_ref=ref, match_date=date(2024, 3, 1),
                                 home_team_ref="alpha", away_team_ref="beta")]
    return ds


# ---- pure contract (no DB) ------------------------------------------------------------------------

def test_sync_source_protocol_and_descriptors():
    class FakeFeed:
        source_system = "online_feed"
        format_id = "generic_json"
        def fetch_new(self, since):
            return sync.SyncBatch(dataset=_dataset(), cursor=sync.SyncCursor("online_feed", last_ref="s1"))
        def fetch_updated(self, since):
            return sync.SyncBatch(dataset=_dataset(), cursor=sync.SyncCursor("online_feed"))

    feed = FakeFeed()
    assert isinstance(feed, sync.SyncSource)                 # runtime-checkable contract
    batch = feed.fetch_new(None)
    assert batch.cursor.last_ref == "s1" and len(batch.dataset.matches) == 1
    job = sync.SyncJob(workspace_id="w", source_system="online_feed", schedule="0 * * * *")
    assert job.mode == sync.REVIEW_REQUIRED and job.enabled is True


def test_invalid_mode_rejected():
    with pytest.raises(ValueError, match="invalid_sync_mode"):
        sync.process_sync_batch(None, "w", ACTOR, _dataset(), mode="whenever")


# ---- orchestration (DB) ---------------------------------------------------------------------------

pytestmark_db = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")


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


@pytestmark_db
def test_review_required_imports_as_draft_only(conn):
    wid = _ws(conn, "SYNC REVIEW")
    out = sync.process_sync_batch(conn, wid, ACTOR, _dataset(), mode=sync.REVIEW_REQUIRED, can_approve=True)
    assert out["auto_approved"] == 0 and out["review_required"] is True
    mid = conn.execute(text("SELECT id FROM match WHERE source_system='online_feed'")).scalar_one()
    assert matches.get_match(conn, mid)["approval_status"] == "draft"   # waits for review


@pytestmark_db
def test_authorised_automatic_approves_and_recalculates(conn):
    wid = _ws(conn, "SYNC AUTO")
    out = sync.process_sync_batch(conn, wid, ACTOR, _dataset(), mode=sync.AUTHORISED_AUTOMATIC, can_approve=True)
    assert out["auto_approved"] == 1 and out["review_required"] is False
    mid = conn.execute(text("SELECT id FROM match WHERE source_system='online_feed'")).scalar_one()
    assert matches.get_match(conn, mid)["approval_status"] == "approved"


@pytestmark_db
def test_authorised_without_permission_stays_draft(conn):
    wid = _ws(conn, "SYNC NOPERM")
    out = sync.process_sync_batch(conn, wid, ACTOR, _dataset(), mode=sync.AUTHORISED_AUTOMATIC, can_approve=False)
    assert out["auto_approved"] == 0 and out["review_required"] is True
    mid = conn.execute(text("SELECT id FROM match WHERE source_system='online_feed'")).scalar_one()
    assert matches.get_match(conn, mid)["approval_status"] == "draft"
