"""Phase 11, Stage 11.5 — secure storage migration + integrity verification.

Migration preserves the stable id, verifies checksums, rolls back on failure and never corrupts/loses
the original. Rolled back; skipped without a live DB.
"""
from __future__ import annotations

import io

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import Settings, get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.media import assets, migration, providers

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "11111111-1111-1111-1111-111111111111"


def _store(tmp_path) -> Settings:
    return Settings(env="test", db_password=None, media_root=str(tmp_path), _env_file=None)


def _png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (200, 60, 60)).save(buf, format="PNG")
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


def test_migration_preserves_stable_id_and_verifies(conn, tmp_path):
    wid = _ws(conn, "MIG OK")
    s = _store(tmp_path)
    a = assets.create_internal_asset(conn, s, wid, ACTOR, raw=_png(), content_type="image/png")
    old_locator = a["storage_locator"]
    out = migration.migrate_asset(conn, s, wid, ACTOR, a["id"], to_provider="internal", remove_source=True)
    assert out["id"] == a["id"]                                   # stable id unchanged -> links intact
    assert out["storage_locator"] != old_locator                 # moved to a new location
    assert out["migration"]["verified"] is True and out["migration"]["source_removed"] is True
    assert providers.internal_provider().path(s, wid, old_locator) is None   # old copy removed after verify
    assert migration.verify_asset(s, wid, assets.get_asset(conn, a["id"]))["ok"] is True


def test_corrupted_source_is_not_migrated(conn, tmp_path):
    wid = _ws(conn, "MIG CORRUPT")
    s = _store(tmp_path)
    a = assets.create_internal_asset(conn, s, wid, ACTOR, raw=_png(), content_type="image/png")
    # tamper the stored original on disk
    path = providers.internal_provider().path(s, wid, a["storage_locator"])
    path.write_bytes(b"tampered")
    assert migration.verify_asset(s, wid, assets.get_asset(conn, a["id"]))["status"] == "mismatch"
    with pytest.raises(ValueError, match="source_integrity_failed"):
        migration.migrate_asset(conn, s, wid, ACTOR, a["id"], to_provider="internal")
    # asset unchanged (locator still the original) -> nothing lost
    assert assets.get_asset(conn, a["id"])["storage_locator"] == a["storage_locator"]


def test_migrate_to_unavailable_onevault_is_graceful(conn, tmp_path):
    wid = _ws(conn, "MIG OV")
    s = _store(tmp_path)
    a = assets.create_internal_asset(conn, s, wid, ACTOR, raw=_png(), content_type="image/png")
    with pytest.raises(providers.ProviderUnavailable):
        migration.migrate_asset(conn, s, wid, ACTOR, a["id"], to_provider="onevault")
    assert assets.get_asset(conn, a["id"])["storage_provider"] == "internal"   # unchanged


def test_external_cannot_be_byte_migrated(conn, tmp_path):
    wid = _ws(conn, "MIG EXT")
    s = _store(tmp_path)
    ext = assets.create_external_reference(conn, wid, ACTOR, url="https://x/y")
    with pytest.raises(ValueError, match="cannot_migrate_external"):
        migration.migrate_asset(conn, s, wid, ACTOR, ext["id"], to_provider="internal")
    a = assets.create_internal_asset(conn, s, wid, ACTOR, raw=_png(), content_type="image/png")
    with pytest.raises(ValueError, match="cannot_migrate_to_external"):
        migration.migrate_asset(conn, s, wid, ACTOR, a["id"], to_provider="external")


def test_verify_external_is_unverifiable(conn, tmp_path):
    wid = _ws(conn, "MIG VER EXT")
    ext = assets.create_external_reference(conn, wid, ACTOR, url="https://x/y")
    v = migration.verify_asset(_store(tmp_path), wid, assets.get_asset(conn, ext["id"]))
    assert v["status"] == "unverifiable" and v["ok"] is None
