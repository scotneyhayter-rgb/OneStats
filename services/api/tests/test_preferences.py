"""Per-user preferences (Part 15) — round-trip + RLS isolation between users.

Rolled back per test; skipped without a live DB; runs as ``onestats_app`` under FORCE RLS. Verifies
that a user can store and read their own dashboard preferences per workspace, and that the
user_preference RLS policy prevents one user seeing another's preferences.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_user
from onestats.domain import preferences

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")


@pytest.fixture
def engine():
    return create_engine(settings.database_url, future=True)


def _mk_user(conn) -> uuid.UUID:
    return conn.execute(
        text("INSERT INTO app_user(username, password_hash) VALUES (:u, 'x') RETURNING id"),
        {"u": f"pref-{uuid.uuid4().hex[:10]}"},
    ).scalar_one()


def test_round_trip_and_rls_isolation(engine):
    ws = uuid.uuid4()
    with engine.begin() as conn:
        u1 = _mk_user(conn)
        u2 = _mk_user(conn)
        # a real workspace so the FK holds
        conn.execute(text("INSERT INTO workspace(id, name, short_name, type) VALUES (:i,'W',:s,'club')"),
                     {"i": ws, "s": f"w-{uuid.uuid4().hex[:8]}"})
    try:
        # u1 saves dashboard prefs for the workspace
        with engine.connect() as conn:
            t = conn.begin()
            set_user(conn, u1)
            preferences.set_preferences(conn, u1, "dashboard", {"hidden": ["activity"]}, ws)
            t.commit()
        # u1 reads them back
        with engine.connect() as conn:
            t = conn.begin()
            set_user(conn, u1)
            got = preferences.get_preferences(conn, u1, "dashboard", ws)
            t.commit()
        assert got == {"hidden": ["activity"]}
        # u2 (different user, same workspace+namespace) sees nothing — RLS isolates per user
        with engine.connect() as conn:
            t = conn.begin()
            set_user(conn, u2)
            other = preferences.get_preferences(conn, u2, "dashboard", ws)
            t.commit()
        assert other == {}
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM app_user WHERE id IN (:a,:b)"), {"a": u1, "b": u2})
            conn.execute(text("DELETE FROM workspace WHERE id = :i"), {"i": ws})


def test_upsert_replaces_prefs(engine):
    with engine.begin() as conn:
        u = _mk_user(conn)
    try:
        with engine.connect() as conn:
            t = conn.begin(); set_user(conn, u)
            preferences.set_preferences(conn, u, "dashboard", {"hidden": ["summary"]}, None)
            preferences.set_preferences(conn, u, "dashboard", {"hidden": []}, None)
            got = preferences.get_preferences(conn, u, "dashboard", None)
            t.commit()
        assert got == {"hidden": []}
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM app_user WHERE id = :i"), {"i": u})
