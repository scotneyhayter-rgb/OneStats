"""Phase 10, Stages 10.17/10.18/10.19/10.20 — worldwide cricket, copyright/access, performance,
OneVault readiness. Rolled back; skipped without a live DB.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import Settings, get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import matches
from onestats.domain.research import reconstruction, sources, storage

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


# --- 10.17 worldwide ---------------------------------------------------------------------------
def test_no_arbitrary_earliest_date_and_any_format(conn):
    wid = _ws(conn, "WW")
    # a 19th-century match, year-precision — no arbitrary floor is imposed
    m = reconstruction.start_reconstruction(conn, wid, ACTOR, match_date=dt.date(1849, 1, 1),
                                            date_precision="year")
    assert str(m["match_date"]) == "1849-01-01" and m["date_precision"] == "year"
    # arbitrary historical formats / classifications are accepted verbatim
    for fmt in ("Test", "ODI", "T20I", "Women's First XI", "Timeless Test"):
        mid = matches.create_match(conn, wid, ACTOR, format=fmt, matchtype=fmt)
        assert matches.get_match(conn, mid)["format"] == fmt


def test_multilingual_source_language_retained(conn):
    wid = _ws(conn, "WW LANG")
    s = sources.create_source(conn, wid, ACTOR, title="Compte rendu du match", source_type="newspaper_article",
                              language="fr")
    assert sources.get_source(conn, s["id"])["language"] == "fr"


# --- 10.18 copyright / access ------------------------------------------------------------------
def test_copyright_and_usage_restrictions_retained(conn):
    wid = _ws(conn, "CR")
    s = sources.create_source(conn, wid, ACTOR, title="Licensed photo", source_type="photograph",
                              copyright_status="in_copyright",
                              usage_restrictions="Internal research only; not for public redistribution")
    got = sources.get_source(conn, s["id"])
    assert got["copyright_status"] == "in_copyright"
    assert "not for public redistribution" in got["usage_restrictions"]


# --- 10.19 performance / pagination ------------------------------------------------------------
def test_source_listing_paginates(conn):
    wid = _ws(conn, "PAGE")
    for i in range(5):
        sources.create_source(conn, wid, ACTOR, title=f"src {i}", source_type="pdf")
    page1 = sources.list_sources(conn, wid, limit=2, offset=0)
    page2 = sources.list_sources(conn, wid, limit=2, offset=2)
    assert len(page1) == 2 and len(page2) == 2
    assert {r["id"] for r in page1}.isdisjoint({r["id"] for r in page2})   # distinct pages


# --- 10.20 OneVault readiness ------------------------------------------------------------------
def test_source_file_metadata_is_portable(conn, tmp_path):
    wid = _ws(conn, "VAULT")
    store = Settings(env="test", db_password=None, media_root=str(tmp_path), _env_file=None)
    stored = storage.store_source_file(store, wid, b"document-bytes", "application/pdf")
    s = sources.create_source(conn, wid, ACTOR, title="doc", source_type="pdf")
    out = sources.set_file(conn, wid, ACTOR, s["id"], file_ref=str(stored["file_ref"]),
                           file_sha256=str(stored["file_sha256"]), file_bytes=int(stored["file_bytes"]),
                           content_type="application/pdf")
    # a stable reference + integrity hash + size travel with the record (ready to link/transfer to OneVault)
    assert out["file_ref"] and out["file_sha256"] and out["file_bytes"] == len(b"document-bytes")
    assert out["content_type"] == "application/pdf"
