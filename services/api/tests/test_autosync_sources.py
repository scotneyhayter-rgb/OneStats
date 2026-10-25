"""Phase 9, Stage 9.2 — connector catalog, fixture connector, and the source registry.

The catalog documents real providers as interface-only (they cannot fetch — nothing fabricated); the
fixture connector yields deterministic batches; the registry stores a workspace's sources with health.
Pure checks need no DB; registry checks roll back.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.autosync import sources
from onestats.domain.autosync.connectors import (
    STATUS_INTERFACE_ONLY,
    FixtureConnector,
    catalog,
)

settings = get_settings()
ACTOR = "11111111-1111-1111-1111-111111111111"

ROWS = [{"Date": "2024-01-06", "HomeTeam": "Alpha CC", "AwayTeam": "Beta CC", "Result": "Home win"}]


# ---- connectors (no DB) ---------------------------------------------------------------------------

def test_real_providers_are_interface_only_and_cannot_fetch():
    described = {d["connector_id"]: d for d in catalog.describe()}
    for cid in ("playhq", "play_cricket", "cricket_archive"):
        assert described[cid]["status"] == STATUS_INTERFACE_ONLY
    conn = catalog.get("playhq")
    with pytest.raises(NotImplementedError, match="not implemented"):
        conn.fetch_new(None)


def test_fixture_connector_yields_deterministic_batches():
    c = FixtureConnector("fixture_feed", ROWS)
    batch = c.fetch_new(None)
    assert len(batch.dataset.matches) == 1 and batch.cursor.last_ref is not None
    assert batch.dataset.provenance.source_system == "fixture_feed"
    # a second poll with the advanced cursor yields nothing new
    assert c.fetch_new(batch.cursor).dataset.matches == []


# ---- source registry (DB) -------------------------------------------------------------------------

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
def test_register_list_enable_and_health(conn):
    wid = _ws(conn, "SRC REG")
    s = sources.register_source(conn, wid, ACTOR, connector_id="fixture_feed", name="Local Fixture",
                                provider="Fixture", access_method="fixture", formats=["One-Day"])
    assert s["reliability"] == "unknown" and s["enabled"] is True
    assert len(sources.list_sources(conn, wid)) == 1
    with pytest.raises(ValueError, match="source_name_exists"):
        sources.register_source(conn, wid, ACTOR, connector_id="fixture_feed", name="Local Fixture")

    sources.record_success(conn, s["id"])
    assert sources.get_source(conn, s["id"])["reliability"] == "ok"
    h = sources.record_health(conn, wid, ACTOR, s["id"], reliability="degraded", notes="slow")
    assert h["reliability"] == "degraded"
    sources.set_enabled(conn, wid, ACTOR, s["id"], False)
    assert sources.list_sources(conn, wid, enabled_only=True) == []


@pytestmark_db
def test_credentials_are_not_stored_only_a_reference(conn):
    wid = _ws(conn, "SRC SECRETS")
    s = sources.register_source(conn, wid, ACTOR, connector_id="playhq", name="PlayHQ",
                                auth_required=True, credentials_ref="secret-store://playhq/key-1")
    # only a reference is persisted — never the secret itself
    assert s["credentials_ref"] == "secret-store://playhq/key-1"


@pytestmark_db
def test_source_workspace_isolation(conn):
    wid_a = _ws(conn, "SRC ISO A")
    sources.register_source(conn, wid_a, ACTOR, connector_id="fixture_feed", name="A Source")
    assert len(sources.list_sources(conn, wid_a)) == 1
    wid_b = conn.execute(text("INSERT INTO workspace(name,type) VALUES ('SRC ISO B','club') RETURNING id")).scalar_one()
    set_workspace(conn, wid_b)
    assert sources.list_sources(conn, wid_b) == []
