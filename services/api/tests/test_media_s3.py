"""S3-compatible object-storage media provider (cloud-prep).

The provider satisfies the same put/get/exists/delete contract as internal storage, so the existing
media-asset migration moves originals to object storage with the verified-copy flow. boto3 is never
needed here: a fake S3 client is injected. DB-backed migration test is skipped without a live DB.
"""
from __future__ import annotations

import io
import uuid

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import Settings, get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.media import assets, migration, providers

ACTOR = "11111111-1111-1111-1111-111111111111"
S = Settings(env="test", db_password=None, _env_file=None, s3_bucket="bkt", s3_prefix="onestats")
NO_S3 = Settings(env="test", db_password=None, _env_file=None)

settings_db = get_settings()
pytestmark_db = pytest.mark.skipif(not settings_db.db_configured, reason="no live database credential configured")


class FakeS3:
    """A tiny in-memory stand-in for a boto3 S3 client (the subset the provider uses)."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], bytes] = {}

    def put_object(self, Bucket, Key, Body, ContentType=None):
        self.store[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):
        if (Bucket, Key) not in self.store:
            raise KeyError(Key)
        return {"Body": io.BytesIO(self.store[(Bucket, Key)])}

    def head_object(self, Bucket, Key):
        if (Bucket, Key) not in self.store:
            raise KeyError(Key)
        return {}

    def delete_object(self, Bucket, Key):
        self.store.pop((Bucket, Key), None)


def test_s3_put_get_exists_delete_roundtrip():
    fake = FakeS3()
    p = providers.S3StorageProvider(client_factory=lambda: fake)
    wid = uuid.uuid4()
    stored = p.put(S, wid, b"hello-bytes", "application/pdf")
    key = stored["locator"]
    assert stored["bytes"] == 11 and stored["sha256"]
    assert key.startswith("onestats/media/") and str(wid) in key and key.endswith(".pdf")  # workspace-partitioned
    assert p.exists(S, wid, key) is True
    assert p.get(S, wid, key) == b"hello-bytes"
    assert p.exists(S, wid, "missing-key") is False
    p.delete(S, wid, key)
    assert p.exists(S, wid, key) is False


def test_s3_get_missing_raises_storage_error():
    p = providers.S3StorageProvider(client_factory=FakeS3)
    with pytest.raises(providers.MediaStorageError):
        p.get(S, uuid.uuid4(), "does-not-exist")


def test_s3_unavailable_without_bucket():
    # No injected client and no bucket configured → unusable, never a silent misconfiguration.
    p = providers.S3StorageProvider()
    with pytest.raises(providers.ProviderUnavailable):
        p.put(NO_S3, uuid.uuid4(), b"x", "application/pdf")


def test_s3_registered_and_described():
    assert "s3" in providers.PROVIDERS
    assert providers.get_provider("s3").name == "s3"
    on = {d["name"]: d for d in providers.describe_providers(S)}["s3"]
    off = {d["name"]: d for d in providers.describe_providers(NO_S3)}["s3"]
    assert on["available"] is True and off["available"] is False


def test_primary_provider_selection():
    from onestats.domain.media import assets
    # default is internal, even when s3 is *configured* but not chosen as the upload target
    assert assets._primary_provider(NO_S3)[1] == "internal"
    assert assets._primary_provider(S)[1] == "internal"
    s3_default = Settings(env="test", db_password=None, _env_file=None, s3_bucket="bkt", media_provider="s3")
    assert assets._primary_provider(s3_default)[1] == "s3"
    # external (register-only) and unknown values fall back to internal
    ext = Settings(env="test", db_password=None, _env_file=None, media_provider="external")
    bad = Settings(env="test", db_password=None, _env_file=None, media_provider="nope")
    assert assets._primary_provider(ext)[1] == "internal"
    assert assets._primary_provider(bad)[1] == "internal"


@pytestmark_db
def test_new_upload_routed_to_s3_with_derivatives(monkeypatch, tmp_path):
    import io

    from PIL import Image
    eng = create_engine(settings_db.database_url, future=True)
    with eng.connect() as conn:
        trans = conn.begin()
        try:
            store = Settings(env="test", db_password=None, media_root=str(tmp_path), _env_file=None,
                             s3_bucket="bkt", media_provider="s3")
            wid = conn.execute(text("INSERT INTO workspace(name, type) VALUES ('S3 UPLOAD','club') RETURNING id")).scalar_one()
            conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a,'s3up') ON CONFLICT (id) DO NOTHING"), {"a": ACTOR})
            set_workspace(conn, wid)
            fake = FakeS3()
            monkeypatch.setattr(providers._S3, "_client_factory", lambda: fake)
            buf = io.BytesIO()
            Image.new("RGB", (80, 60), "blue").save(buf, "PNG")
            asset = assets.create_internal_asset(conn, store, wid, ACTOR, raw=buf.getvalue(),
                                                 content_type="image/png", original_filename="p.png")
            assert asset["storage_provider"] == "s3"           # new upload went to object storage
            assert asset["thumbnail_ref"]                      # derivative generated + stored on s3
            # original and thumbnail both retrievable from object storage
            assert providers.get_provider("s3").get(store, wid, asset["storage_locator"])
            assert providers.get_provider("s3").get(store, wid, asset["thumbnail_ref"])
        finally:
            trans.rollback()
    eng.dispose()


@pytestmark_db
def test_migrate_internal_asset_to_s3(monkeypatch, tmp_path):
    eng = create_engine(settings_db.database_url, future=True)
    with eng.connect() as conn:
        trans = conn.begin()
        try:
            store = Settings(env="test", db_password=None, media_root=str(tmp_path), _env_file=None, s3_bucket="bkt")
            wid = conn.execute(text("INSERT INTO workspace(name, type) VALUES ('S3 MIG','club') RETURNING id")).scalar_one()
            conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a,'s3actor') ON CONFLICT (id) DO NOTHING"), {"a": ACTOR})
            set_workspace(conn, wid)
            asset = assets.create_internal_asset(conn, store, wid, ACTOR, raw=b"%PDF-1.4 fake bytes",
                                                 content_type="application/pdf", original_filename="clip.pdf")
            # route the registry's s3 provider at a fake client, then migrate internal -> s3
            fake = FakeS3()
            monkeypatch.setattr(providers._S3, "_client_factory", lambda: fake)
            out = migration.migrate_asset(conn, store, wid, ACTOR, uuid.UUID(str(asset["id"])),
                                          to_provider="s3", remove_source=True)
            assert out["storage_provider"] == "s3"
            # the bytes are now served from object storage, intact
            got = providers.get_provider("s3").get(store, wid, out["storage_locator"])
            assert got == b"%PDF-1.4 fake bytes"
        finally:
            trans.rollback()
    eng.dispose()
