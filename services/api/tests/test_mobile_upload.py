"""Mobile upload (deliverable 20a) — pairing sessions, token security, upload pipeline, isolation.

DB-backed tests run in a rolled-back transaction under FORCE RLS with a tmp media root (originals are
really written); skipped without a DB. Covers: short-lived scoped tokens (hashed at rest, never returned
in listings), expiry + revocation, content-verified type allowlist, size limit, unassigned-for-review
storage, workspace isolation, and API route wiring + token auth.
"""
from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import Settings, get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import mobile_upload

settings = get_settings()
dbmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "11111111-1111-1111-1111-111111111111"


def _store(tmp_path, **kw) -> Settings:
    return Settings(env="test", db_password=None, media_root=str(tmp_path), _env_file=None, **kw)


def _png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (10, 120, 60)).save(buf, format="PNG")
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


@dbmark
def test_create_session_returns_token_once_and_hides_it_in_listings(conn):
    wid = _ws(conn, "MU TOKEN")
    out = mobile_upload.create_session(conn, wid, ACTOR, ttl_minutes=30)
    assert out["token"] and out["active"] is True
    # the raw token is never stored in plaintext — only its hash
    stored_hash = conn.execute(text("SELECT token_hash FROM upload_session WHERE id = :i"), {"i": out["id"]}).scalar_one()
    assert stored_hash != out["token"] and len(stored_hash) == 64
    # listings never expose the token or its hash
    listed = mobile_upload.list_sessions(conn, wid)
    assert all("token" not in s and "token_hash" not in s for s in listed)


@dbmark
def test_resolve_token_accepts_correct_rejects_wrong(conn):
    wid = _ws(conn, "MU RESOLVE")
    out = mobile_upload.create_session(conn, wid, ACTOR)
    sid = uuid.UUID(out["id"])
    assert mobile_upload.resolve_token(conn, wid, sid, out["token"]) is not None
    assert mobile_upload.resolve_token(conn, wid, sid, "wrong-token") is None
    assert mobile_upload.resolve_token(conn, wid, sid, "") is None


@dbmark
def test_expired_and_revoked_sessions_do_not_resolve(conn):
    wid = _ws(conn, "MU EXPIRE")
    out = mobile_upload.create_session(conn, wid, ACTOR)
    sid = uuid.UUID(out["id"])
    conn.execute(text("UPDATE upload_session SET expires_at = :e WHERE id = :i"),
                 {"e": datetime.now(UTC) - timedelta(minutes=1), "i": sid})
    assert mobile_upload.resolve_token(conn, wid, sid, out["token"]) is None   # expired

    out2 = mobile_upload.create_session(conn, wid, ACTOR)
    sid2 = uuid.UUID(out2["id"])
    mobile_upload.revoke_session(conn, wid, ACTOR, sid2)
    assert mobile_upload.resolve_token(conn, wid, sid2, out2["token"]) is None  # revoked


@dbmark
def test_accept_upload_stores_image_unassigned_for_review(conn, tmp_path):
    wid = _ws(conn, "MU UPLOAD")
    s = _store(tmp_path)
    out = mobile_upload.create_session(conn, wid, ACTOR)
    session = mobile_upload.resolve_token(conn, wid, uuid.UUID(out["id"]), out["token"])
    res = mobile_upload.accept_upload(conn, s, wid, session, raw=_png(), content_type="image/png", filename="p.png")
    assert res["kind"] == "photo" and res["status"] == "received_for_review"
    # the stored asset exists, is mobile-provenance, private, and NOT linked to any entity (review queue)
    row = conn.execute(text("SELECT source_provenance, visibility FROM media_asset WHERE id = :i"),
                       {"i": res["asset_id"]}).mappings().one()
    assert row["source_provenance"] == "mobile_upload" and row["visibility"] == "private"
    links = conn.execute(text("SELECT count(*) FROM media_link WHERE media_asset_id = :i"), {"i": res["asset_id"]}).scalar_one()
    assert links == 0
    # the session upload counter advanced
    assert conn.execute(text("SELECT upload_count FROM upload_session WHERE id = :i"), {"i": out["id"]}).scalar_one() == 1


@dbmark
def test_accept_upload_accepts_pdf_and_rejects_unknown_type(conn, tmp_path):
    wid = _ws(conn, "MU TYPES")
    s = _store(tmp_path)
    out = mobile_upload.create_session(conn, wid, ACTOR)
    session = mobile_upload.resolve_token(conn, wid, uuid.UUID(out["id"]), out["token"])
    pdf = mobile_upload.accept_upload(conn, s, wid, session, raw=b"%PDF-1.4 minimal", content_type="application/pdf", filename="d.pdf")
    assert pdf["kind"] == "document" and pdf["content_type"] == "application/pdf"
    with pytest.raises(ValueError, match="unsupported_file_type"):
        mobile_upload.accept_upload(conn, s, wid, session, raw=b"not an image or pdf", content_type="image/png", filename="x.png")


@dbmark
def test_accept_upload_enforces_size_limit(conn, tmp_path):
    wid = _ws(conn, "MU SIZE")
    s = _store(tmp_path, max_media_bytes=10)      # tiny limit
    out = mobile_upload.create_session(conn, wid, ACTOR)
    session = mobile_upload.resolve_token(conn, wid, uuid.UUID(out["id"]), out["token"])
    with pytest.raises(ValueError, match="file_too_large"):
        mobile_upload.accept_upload(conn, s, wid, session, raw=_png(), content_type="image/png", filename="big.png")


@dbmark
def test_sessions_isolated_across_workspaces(conn):
    wid_a = conn.execute(text("INSERT INTO workspace(name, type) VALUES ('MU ISO A','club') RETURNING id")).scalar_one()
    wid_b = conn.execute(text("INSERT INTO workspace(name, type) VALUES ('MU ISO B','club') RETURNING id")).scalar_one()
    set_workspace(conn, wid_a)
    out = mobile_upload.create_session(conn, wid_a, ACTOR)
    sid = uuid.UUID(out["id"])
    # from workspace B the session cannot be seen or resolved (RLS)
    set_workspace(conn, wid_b)
    assert mobile_upload.list_sessions(conn, wid_b) == []
    assert mobile_upload.resolve_token(conn, wid_b, sid, out["token"]) is None


# --- API wiring / auth (no DB) ---
def _client():
    from fastapi.testclient import TestClient

    from onestats.main import create_app
    return TestClient(create_app(Settings(env="test", db_password=None, _env_file=None)))


def test_mobile_upload_routes_registered():
    paths = set(_client().app.openapi()["paths"].keys())
    assert "/api/v1/workspaces/{workspace_id}/mobile-upload/sessions" in paths
    assert "/api/v1/upload/{workspace_id}/{session_id}" in paths


def test_pairing_requires_auth_and_upload_requires_token():
    client = _client()
    wid, sid = uuid.uuid4(), uuid.uuid4()
    # pairing needs a bearer session
    assert client.get(f"/api/v1/workspaces/{wid}/mobile-upload/sessions").status_code == 401
    # upload needs the pairing token (401 without it) — never a bearer session
    assert client.get(f"/api/v1/upload/{wid}/{sid}").status_code == 401
    assert client.post(f"/api/v1/upload/{wid}/{sid}").status_code in (401, 422)
