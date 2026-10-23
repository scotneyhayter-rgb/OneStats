"""Live branding tests (rolled back; skipped without a DB)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import branding, workspaces

settings = get_settings()
pytestmark = pytest.mark.skipif(
    not settings.db_configured, reason="no live database credential configured"
)


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


def _mk(conn):
    actor = conn.execute(
        text("INSERT INTO app_user(username) VALUES ('branduser') RETURNING id")
    ).scalar_one()
    ws = workspaces.create_workspace(conn, "Brand WS", "brandws", "club", actor)
    return actor, ws


def test_set_get_resolve_and_audit(conn):
    actor, ws = _mk(conn)
    after = branding.set_branding(
        conn, ws, actor,
        {"primary_colour": "#0b1120", "accent_colour": "#3b82f6", "theme_mode": "dark",
         "tagline": "Since 1891"},
    )
    assert after["primary_colour"] == "#0b1120" and after["theme_mode"] == "dark"
    resolved = branding.resolve_tokens(after)
    assert resolved["colours"]["primary_colour"]["foreground"] == "#ffffff"
    assert resolved["colours"]["primary_colour"]["meets_aa"] is True
    pub = branding.published_payload(ws, after)
    assert pub["tagline"] == "Since 1891"
    assert conn.execute(
        text("SELECT count(*) FROM audit_log WHERE action = 'branding.update'")
    ).scalar_one() >= 1


def test_invalid_colour_rejected(conn):
    actor, ws = _mk(conn)
    with pytest.raises(ValueError, match="invalid_colour:primary_colour"):
        branding.set_branding(conn, ws, actor, {"primary_colour": "not-a-colour"})


def test_reset_removes_branding(conn):
    actor, ws = _mk(conn)
    branding.set_branding(conn, ws, actor, {"primary_colour": "#123456"})
    branding.reset_branding(conn, ws, actor)
    assert branding.get_branding(conn, ws) is None


def test_branding_isolated_across_workspaces(conn):
    actor, ws_a = _mk(conn)
    branding.set_branding(conn, ws_a, actor, {"primary_colour": "#123456"})
    ws_b = workspaces.create_workspace(conn, "Brand WS B", "brandwsb", "club", actor)
    # Under workspace B's context, workspace A's branding row is invisible (RLS).
    set_workspace(conn, ws_b)
    assert branding.get_branding(conn, ws_a) is None
