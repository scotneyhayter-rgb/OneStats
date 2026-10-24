"""Workspace-configurable match formats (Phase 7, Stage 7.5).

Rolled back per test; skipped without a live DB; runs as ``onestats_app`` under FORCE RLS. Covers
seeding, enabled-only listing, enable/disable, default selection, custom formats, preservation of a
match whose format is later disabled, and workspace isolation.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import competitions, match_formats, matches

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
    set_workspace(conn, wid)
    return wid


def _by_code(formats):
    return {f["code"]: f for f in formats}


def test_seeds_standard_formats_idempotently(conn):
    wid = _ws(conn, "FMT SEED")
    a = match_formats.list_formats(conn, wid)
    assert len(a) == len(match_formats.STANDARD_FORMATS)
    assert {"test", "t20", "two_day", "one_day", "other"} <= set(_by_code(a))
    match_formats.list_formats(conn, wid)  # again
    assert conn.execute(text("SELECT count(*) FROM match_format WHERE workspace_id = :w"), {"w": wid}).scalar_one() == len(match_formats.STANDARD_FORMATS)


def test_enable_disable_and_enabled_only_listing(conn):
    wid = _ws(conn, "FMT ENABLE")
    t20 = _by_code(match_formats.list_formats(conn, wid))["t20"]
    match_formats.set_enabled(conn, wid, ACTOR, t20["id"], False)
    enabled_codes = {f["code"] for f in match_formats.list_formats(conn, wid, enabled_only=True)}
    assert "t20" not in enabled_codes and "two_day" in enabled_codes


def test_default_selection_single_and_not_disabled(conn):
    wid = _ws(conn, "FMT DEFAULT")
    codes = _by_code(match_formats.list_formats(conn, wid))
    match_formats.set_default(conn, wid, ACTOR, codes["one_day"]["id"])
    match_formats.set_default(conn, wid, ACTOR, codes["two_day"]["id"])   # moves the default
    defaults = [f for f in match_formats.list_formats(conn, wid) if f["is_default"]]
    assert len(defaults) == 1 and defaults[0]["code"] == "two_day"
    assert match_formats.default_format_label(conn, wid) == "Two-Day"
    # a disabled format cannot be made the default; disabling the default clears it
    match_formats.set_enabled(conn, wid, ACTOR, codes["test"]["id"], False)
    with pytest.raises(ValueError, match="cannot_default_disabled_format"):
        match_formats.set_default(conn, wid, ACTOR, codes["test"]["id"])
    match_formats.set_enabled(conn, wid, ACTOR, codes["two_day"]["id"], False)   # disable the current default
    assert match_formats.default_format_label(conn, wid) is None


def test_create_custom_format(conn):
    wid = _ws(conn, "FMT CUSTOM")
    match_formats.list_formats(conn, wid)
    c = match_formats.create_custom(conn, wid, ACTOR, "Super Eights")
    assert c["code"] == "super_eights" and c["is_custom"] is True and c["enabled"] is True
    # a second with the same label gets a distinct code
    c2 = match_formats.create_custom(conn, wid, ACTOR, "Super Eights")
    assert c2["code"] != c["code"]


def test_disabling_a_format_preserves_matches_using_it(conn):
    wid = _ws(conn, "FMT PRESERVE")
    cid = competitions.create_competition(conn, wid, ACTOR, name="League")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=cid, format="Two-Day")
    codes = _by_code(match_formats.list_formats(conn, wid))
    match_formats.set_enabled(conn, wid, ACTOR, codes["two_day"]["id"], False)   # disable it afterwards
    assert matches.get_match(conn, mid)["format"] == "Two-Day"                   # historical match preserved


def test_isolation(conn):
    wid_a = conn.execute(text("INSERT INTO workspace(name,type) VALUES ('FMT ISO A','club') RETURNING id")).scalar_one()
    set_workspace(conn, wid_a)
    match_formats.list_formats(conn, wid_a)   # seed A
    wid_b = conn.execute(text("INSERT INTO workspace(name,type) VALUES ('FMT ISO B','club') RETURNING id")).scalar_one()
    set_workspace(conn, wid_b)
    match_formats.list_formats(conn, wid_b)   # seed B
    # B sees only its own formats, not A's (FORCE RLS), and B's count equals the standard set
    assert conn.execute(text("SELECT count(*) FROM match_format")).scalar_one() == len(match_formats.STANDARD_FORMATS)
