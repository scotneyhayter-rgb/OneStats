"""Phase 11, Stage 11.9 — promote a Phase 10 research source into a canonical media asset.

One file, one media record: the file is moved into the media store, the research source points at the
asset, and there is no duplicate. Rolled back; skipped without a live DB.
"""
from __future__ import annotations

import hashlib
import io

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import Settings, get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.media import assets, integration
from onestats.domain.research import sources as rsources
from onestats.domain.research import storage as rstorage

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "11111111-1111-1111-1111-111111111111"


def _store(tmp_path) -> Settings:
    return Settings(env="test", db_password=None, media_root=str(tmp_path), _env_file=None)


def _png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (28, 28), (140, 80, 40)).save(buf, format="PNG")
    return buf.getvalue()


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


def _research_source_with_file(conn, s, wid, raw):
    src = rsources.create_source(conn, wid, ACTOR, title="1931 clipping", source_type="newspaper_clipping",
                                 copyright_status="public_domain")
    stored = rstorage.store_source_file(s, wid, raw, "image/png")
    rsources.set_file(conn, wid, ACTOR, src["id"], file_ref=str(stored["file_ref"]),
                      file_sha256=str(stored["file_sha256"]), file_bytes=int(stored["file_bytes"]),
                      content_type="image/png")
    return rsources.get_source(conn, src["id"])


def test_promote_moves_file_no_duplicate(conn, tmp_path):
    wid = _ws(conn, "PROMOTE")
    s = _store(tmp_path)
    raw = _png()
    src = _research_source_with_file(conn, s, wid, raw)
    old_ref = src["file_ref"]

    asset = integration.promote_research_source(conn, s, wid, ACTOR, src["id"])
    assert asset["storage_provider"] == "internal"
    assert asset["sha256"] == hashlib.sha256(raw).hexdigest()
    assert asset["source_provenance"] == f"research_source:{src['id']}"

    # the research source now points at the asset and no longer holds its own file (moved, not duplicated)
    refreshed = rsources.get_source(conn, src["id"])
    assert str(refreshed["media_asset_id"]) == str(asset["id"]) and refreshed["file_ref"] is None
    assert rstorage.source_file_path(s, wid, old_ref) is None   # research file moved out
    # linked back to the source
    linked = assets.list_assets_for_entity(conn, wid, "research_source", src["id"])
    assert len(linked) == 1 and str(linked[0]["id"]) == str(asset["id"])
    # the promoted asset's bytes are intact
    assert assets.asset_bytes(s, wid, assets.get_asset(conn, asset["id"])) == raw


def test_promote_is_idempotent(conn, tmp_path):
    wid = _ws(conn, "PROMOTE IDEM")
    s = _store(tmp_path)
    src = _research_source_with_file(conn, s, wid, _png())
    first = integration.promote_research_source(conn, s, wid, ACTOR, src["id"])
    second = integration.promote_research_source(conn, s, wid, ACTOR, src["id"])
    assert str(first["id"]) == str(second["id"])   # same canonical asset, no duplicate


def test_promote_requires_a_file(conn, tmp_path):
    wid = _ws(conn, "PROMOTE NOFILE")
    s = _store(tmp_path)
    src = rsources.create_source(conn, wid, ACTOR, title="no file", source_type="manual_reference")
    with pytest.raises(ValueError, match="source_has_no_file"):
        integration.promote_research_source(conn, s, wid, ACTOR, src["id"])
