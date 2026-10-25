"""Phase 11, Stage 11.8 — media backup manifest + integrity verification.

Checksum validation, missing-file detection and relationship preservation. Rolled back; skipped without
a live DB.
"""
from __future__ import annotations

import io

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import Settings, get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.media import assets, backup, providers

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "11111111-1111-1111-1111-111111111111"


def _store(tmp_path) -> Settings:
    return Settings(env="test", db_password=None, media_root=str(tmp_path), _env_file=None)


def _png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (30, 30), (30, 160, 160)).save(buf, format="PNG")
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


def test_verify_media_detects_missing_and_mismatch(conn, tmp_path):
    wid = _ws(conn, "BK VERIFY")
    s = _store(tmp_path)
    good = assets.create_internal_asset(conn, s, wid, ACTOR, raw=_png(), content_type="image/png")
    tampered = assets.create_internal_asset(conn, s, wid, ACTOR, raw=_png(), content_type="image/png")
    gone = assets.create_internal_asset(conn, s, wid, ACTOR, raw=_png(), content_type="image/png")
    # tamper one, delete another's file
    providers.internal_provider().path(s, wid, tampered["storage_locator"]).write_bytes(b"xx")
    providers.internal_provider().path(s, wid, gone["storage_locator"]).unlink()

    rep = backup.verify_media(conn, s, wid)
    assert str(tampered["id"]) in rep["mismatch"]
    assert str(gone["id"]) in rep["missing"]
    assert str(good["id"]) not in rep["mismatch"] and str(good["id"]) not in rep["missing"]
    assert rep["ok"] is False


def test_manifest_includes_assets_links_and_integrity(conn, tmp_path):
    wid = _ws(conn, "BK MANIFEST")
    s = _store(tmp_path)
    a = assets.create_internal_asset(conn, s, wid, ACTOR, raw=_png(), content_type="image/png")
    match_id = conn.execute(text("INSERT INTO match(workspace_id) VALUES (:w) RETURNING id"), {"w": wid}).scalar_one()
    assets.link_asset(conn, wid, ACTOR, a["id"], entity_type="match", entity_id=match_id)
    m = backup.build_manifest(conn, s, wid)
    assert m["asset_count"] == 1
    assert m["assets"][0]["sha256"] == a["sha256"] and m["assets"][0]["integrity"] == "ok"
    assert any(lk["entity_type"] == "match" for lk in m["links"])   # relationships preserved in the manifest
    assert m["integrity"]["ok"] is True


def test_check_restore_against_manifest(conn, tmp_path):
    wid = _ws(conn, "BK RESTORE")
    s = _store(tmp_path)
    a = assets.create_internal_asset(conn, s, wid, ACTOR, raw=_png(), content_type="image/png")
    match_id = conn.execute(text("INSERT INTO match(workspace_id) VALUES (:w) RETURNING id"), {"w": wid}).scalar_one()
    assets.link_asset(conn, wid, ACTOR, a["id"], entity_type="match", entity_id=match_id)
    manifest = backup.build_manifest(conn, s, wid)
    # live archive matches the manifest -> ok
    assert backup.check_restore(conn, s, wid, manifest)["ok"] is True
    # remove the link -> relationship reported missing
    conn.execute(text("DELETE FROM media_link WHERE workspace_id = :w"), {"w": wid})
    chk = backup.check_restore(conn, s, wid, manifest)
    assert chk["ok"] is False and len(chk["relationships_missing"]) == 1
