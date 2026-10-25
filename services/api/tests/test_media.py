"""Phase 11, Stages 11.1-11.4 — media providers + assets.

Internal provider round-trip + traversal safety and OneVault capability detection need no DB. Asset
CRUD / links / isolation use a live DB (rolled back; skipped without one). A tmp media root backs file
storage so originals are really written and read.
"""
from __future__ import annotations

import io

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import Settings, get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.media import assets, providers

settings = get_settings()
ACTOR = "11111111-1111-1111-1111-111111111111"


def _store(tmp_path) -> Settings:
    return Settings(env="test", db_password=None, media_root=str(tmp_path), _env_file=None)


def _png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (10, 120, 60)).save(buf, format="PNG")
    return buf.getvalue()


# --- providers (no DB) ---------------------------------------------------------------------------
def test_internal_provider_round_trip_and_traversal(tmp_path):
    s = _store(tmp_path)
    p = providers.internal_provider()
    import uuid
    wid = uuid.uuid4()
    out = p.put(s, wid, b"original-bytes", "application/pdf")
    assert p.exists(s, wid, out["locator"]) and p.get(s, wid, out["locator"]) == b"original-bytes"
    assert p.path(s, wid, "../escape.pdf") is None   # traversal guarded


def test_onevault_is_capability_detected_and_unavailable_by_default(tmp_path):
    s = _store(tmp_path)
    ov = providers.onevault_provider()
    cap = ov.detect_capabilities(s)
    assert cap["available"] is False and "No verified OneVault API" in cap["reason"]
    with pytest.raises(providers.ProviderUnavailable):
        import uuid
        ov.get(s, uuid.uuid4(), "obj-1")


def test_describe_providers(tmp_path):
    desc = {p["name"]: p for p in providers.describe_providers(_store(tmp_path))}
    assert desc["internal"]["available"] and desc["internal"]["default"]
    assert desc["external"]["available"] and not desc["external"]["default"]
    assert desc["onevault"]["available"] is False   # not operational until a verified API


# --- assets (DB) ---------------------------------------------------------------------------------
dbmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")


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
def test_internal_asset_preserves_original_and_derives_thumbnail(conn, tmp_path):
    wid = _ws(conn, "MEDIA INT")
    s = _store(tmp_path)
    raw = _png()
    a = assets.create_internal_asset(conn, s, wid, ACTOR, raw=raw, content_type="image/png",
                                     original_filename="scorecard.png", kind="scorecard", title="1931 final")
    assert a["sha256"] and a["file_bytes"] == len(raw) and a["storage_provider"] == "internal"
    assert a["thumbnail_ref"] and a["preview_ref"]           # derivatives generated separately
    assert a["duplicate_of"] is None
    # the original round-trips byte-for-byte (preserved, not re-encoded)
    assert assets.asset_bytes(s, wid, assets.get_asset(conn, a["id"])) == raw


@dbmark
def test_duplicate_content_detected(conn, tmp_path):
    wid = _ws(conn, "MEDIA DUP")
    s = _store(tmp_path)
    raw = _png()
    first = assets.create_internal_asset(conn, s, wid, ACTOR, raw=raw, content_type="image/png")
    second = assets.create_internal_asset(conn, s, wid, ACTOR, raw=raw, content_type="image/png")
    assert second["duplicate_of"] == str(first["id"])   # flagged, not blocked


@dbmark
def test_external_reference_not_fetched(conn, tmp_path):
    wid = _ws(conn, "MEDIA EXT")
    a = assets.create_external_reference(conn, wid, ACTOR, url="https://archive.example/doc/123",
                                         kind="archived_website", title="NLA record")
    assert a["storage_provider"] == "external" and a["storage_locator"].endswith("/123")
    with pytest.raises(providers.ProviderUnavailable):
        assets.asset_bytes(_store(tmp_path), wid, assets.get_asset(conn, a["id"]))


@dbmark
def test_publication_is_explicit_not_implied(conn, tmp_path):
    wid = _ws(conn, "MEDIA PUB")
    s = _store(tmp_path)
    a = assets.create_internal_asset(conn, s, wid, ACTOR, raw=_png(), content_type="image/png")
    assert a["visibility"] == "workspace" and a["publication_eligible"] is False   # internal access != publish
    upd = assets.update_metadata(conn, wid, ACTOR, a["id"], visibility="publishable", publication_eligible=True,
                                 copyright_status="public_domain")
    assert upd["publication_eligible"] is True and upd["visibility"] == "publishable"
    with pytest.raises(ValueError, match="invalid_visibility"):
        assets.update_metadata(conn, wid, ACTOR, a["id"], visibility="everywhere")


@dbmark
def test_stable_id_links_survive(conn, tmp_path):
    wid = _ws(conn, "MEDIA LINK")
    s = _store(tmp_path)
    import uuid
    match_id = conn.execute(text("INSERT INTO match(workspace_id) VALUES (:w) RETURNING id"), {"w": wid}).scalar_one()
    a = assets.create_internal_asset(conn, s, wid, ACTOR, raw=_png(), content_type="image/png")
    assets.link_asset(conn, wid, ACTOR, a["id"], entity_type="match", entity_id=match_id, role="evidence")
    linked = assets.list_assets_for_entity(conn, wid, "match", match_id)
    assert len(linked) == 1 and str(linked[0]["id"]) == str(a["id"])
    with pytest.raises(ValueError, match="invalid_entity_type"):
        assets.link_asset(conn, wid, ACTOR, a["id"], entity_type="spaceship", entity_id=uuid.uuid4())


@dbmark
def test_publication_clearance_is_guarded(conn, tmp_path):
    wid = _ws(conn, "MEDIA CLEAR")
    s = _store(tmp_path)
    # junior-protected cannot be published
    j = assets.create_internal_asset(conn, s, wid, ACTOR, raw=_png(), content_type="image/png",
                                     junior_protected=True, copyright_status="public_domain")
    with pytest.raises(ValueError, match="publication_blocked_junior"):
        assets.update_metadata(conn, wid, ACTOR, j["id"], publication_eligible=True, visibility="publishable")
    # sensitive cannot be published
    se = assets.create_internal_asset(conn, s, wid, ACTOR, raw=_png(), content_type="image/png",
                                      sensitive=True, copyright_status="public_domain")
    with pytest.raises(ValueError, match="publication_blocked_sensitive"):
        assets.update_metadata(conn, wid, ACTOR, se["id"], publication_eligible=True)
    # no copyright recorded -> cannot be published
    nc = assets.create_internal_asset(conn, s, wid, ACTOR, raw=_png(), content_type="image/png")
    with pytest.raises(ValueError, match="publication_requires_copyright"):
        assets.update_metadata(conn, wid, ACTOR, nc["id"], publication_eligible=True)
    # a cleared asset is publishable; the protected ones are excluded
    ok = assets.create_internal_asset(conn, s, wid, ACTOR, raw=_png(), content_type="image/png",
                                      copyright_status="public_domain")
    assets.update_metadata(conn, wid, ACTOR, ok["id"], publication_eligible=True, visibility="publishable")
    pub = {str(a["id"]) for a in assets.publishable_assets(conn, wid)}
    assert str(ok["id"]) in pub and str(j["id"]) not in pub and str(se["id"]) not in pub


@dbmark
def test_media_workspace_isolation(conn, tmp_path):
    wa = _ws(conn, "MEDIA ISO A")
    assets.create_internal_asset(conn, _store(tmp_path), wa, ACTOR, raw=_png(), content_type="image/png")
    wb = _ws(conn, "MEDIA ISO B")
    assert assets.list_assets(conn, wb) == []
