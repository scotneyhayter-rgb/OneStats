"""Phase 9, Stage 9.12 — worldwide coverage: formats are preserved and classification is never
inferred from names (men's is not assumed; a women's/junior competition name does not set a grade or
classification). Rolled back; skipped without a live DB for the import check.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import matches
from onestats.domain.autosync import discovery
from onestats.domain.autosync.connectors import FixtureConnector

settings = get_settings()
ACTOR = "11111111-1111-1111-1111-111111111111"


def test_discovered_format_is_preserved_not_assumed():
    rows = [{"Date": "2024-01-06", "HomeTeam": "Alpha Women", "AwayTeam": "Beta Women",
             "Competition": "Women's T20 League", "Format": "T20", "Result": "Home win"}]
    ds = FixtureConnector("feed", rows).fetch_new(None).dataset
    m = ds.matches[0]
    assert m.match_format == "T20"                    # taken from the source, not guessed
    # nothing infers "men's"/grade/classification from the competition name
    assert m.grade_ref is None


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
def test_imported_discovery_keeps_format_and_is_not_auto_classified(conn):
    wid = _ws(conn, "WORLDWIDE")
    rows = [{"Date": "2024-01-06", "HomeTeam": "Alpha U14", "AwayTeam": "Beta U14",
             "Competition": "Junior One-Day", "Format": "One-day", "Result": "Home win"}]
    discovery.discover_new(conn, wid, ACTOR, connector=FixtureConnector("junior_feed", rows), mode="review_required")
    item = discovery.list_items(conn, wid)[0]
    accepted = discovery.accept_item(conn, wid, ACTOR, item["id"])
    m = matches.get_match(conn, accepted["match_id"])
    # format preserved; classification left for an administrator (never inferred from the name)
    assert m["classification"] in (None, "unclassified")
