"""Phase 11, Stage 11.7 — Club Heritage Collection. Rolled back; skipped without a live DB."""
from __future__ import annotations

import io

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import Settings, get_settings
from onestats.db.workspace import set_workspace
from onestats.domain.media import assets, heritage

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "11111111-1111-1111-1111-111111111111"


def _store(tmp_path) -> Settings:
    return Settings(env="test", db_password=None, media_root=str(tmp_path), _env_file=None)


def _png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (90, 90, 160)).save(buf, format="PNG")
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


def test_collection_and_items(conn, tmp_path):
    wid = _ws(conn, "HERITAGE")
    s = _store(tmp_path)
    col = heritage.create_collection(conn, wid, ACTOR, name="RMCC Heritage", description="Founding era")
    a = assets.create_internal_asset(conn, s, wid, ACTOR, raw=_png(), content_type="image/png")
    it = heritage.add_item(conn, wid, ACTOR, col["id"], media_asset_id=a["id"], title="1891 team photo",
                           significance="Earliest known RMCC photograph", display_order=1)
    assert it["significance"].startswith("Earliest known")
    items = heritage.list_items(conn, wid, col["id"])
    assert len(items) == 1
    assert heritage.list_collections(conn, wid)[0]["items"] == 1


def test_item_publication_requires_cleared_asset(conn, tmp_path):
    wid = _ws(conn, "HERITAGE PUB")
    s = _store(tmp_path)
    col = heritage.create_collection(conn, wid, ACTOR, name="Heritage")
    a = assets.create_internal_asset(conn, s, wid, ACTOR, raw=_png(), content_type="image/png")
    it = heritage.add_item(conn, wid, ACTOR, col["id"], media_asset_id=a["id"], title="x")
    # asset not yet cleared -> item cannot be publication-eligible
    with pytest.raises(ValueError, match="asset_not_cleared_for_publication"):
        heritage.update_item(conn, wid, ACTOR, it["id"], publication_eligible=True)
    # clear the asset, then the item can be marked publishable
    assets.update_metadata(conn, wid, ACTOR, a["id"], copyright_status="public_domain",
                           visibility="publishable", publication_eligible=True)
    ok = heritage.update_item(conn, wid, ACTOR, it["id"], publication_eligible=True)
    assert ok["publication_eligible"] is True


def test_heritage_requires_name(conn, tmp_path):
    wid = _ws(conn, "HERITAGE VAL")
    with pytest.raises(ValueError, match="name_required"):
        heritage.create_collection(conn, wid, ACTOR, name="  ")
