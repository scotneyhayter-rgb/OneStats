"""Automatic season assignment (Phase 7, Stage 7.4).

Rolled back per test; skipped without a live DB; runs as ``onestats_app`` under FORCE RLS. Covers
the Australian-summer, calendar and UK-summer models, custom/imported season date ranges, the
unresolved (unknown rule) case, manual-override preservation and idempotency.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import competitions, matches, seasons

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


def _match(conn, wid, comp, d):
    return matches.create_match(conn, wid, ACTOR, competition_id=comp, match_date=d)


def test_au_summer_assignment_examples(conn):
    wid = _ws(conn, "SZN AU")
    comp = competitions.create_competition(conn, wid, ACTOR, name="Summer League", season_model="au_summer")
    for d, expected in [(date(2019, 10, 19), "2019/20"), (date(2020, 2, 15), "2019/20"), (date(2026, 10, 24), "2026/27")]:
        mid = _match(conn, wid, comp, d)
        out = seasons.auto_assign_season(conn, wid, ACTOR, mid)
        assert out["applied"] is True
        m = matches.get_match(conn, mid)
        label = conn.execute(text("SELECT label FROM season WHERE id = :s"), {"s": m["season_id"]}).scalar_one()
        assert label == expected and m["season_source"] == "calculated"


def test_calendar_year_assignment(conn):
    wid = _ws(conn, "SZN CAL")
    comp = competitions.create_competition(conn, wid, ACTOR, name="Calendar Cup", season_model="calendar")
    mid = _match(conn, wid, comp, date(2020, 6, 1))
    seasons.auto_assign_season(conn, wid, ACTOR, mid)
    m = matches.get_match(conn, mid)
    assert conn.execute(text("SELECT label FROM season WHERE id = :s"), {"s": m["season_id"]}).scalar_one() == "2020"


def test_custom_uses_existing_season_date_range(conn):
    wid = _ws(conn, "SZN CUSTOM")
    comp = competitions.create_competition(conn, wid, ACTOR, name="Custom", season_model="custom")
    sid = competitions.create_season(conn, wid, ACTOR, comp, label="2019-20 Special",
                                     start_date=date(2019, 9, 1), end_date=date(2020, 4, 30))
    mid = _match(conn, wid, comp, date(2020, 1, 15))
    out = seasons.auto_assign_season(conn, wid, ACTOR, mid)
    assert out["applied"] is True and matches.get_match(conn, mid)["season_id"] == sid  # covering season used


def test_unknown_model_is_unresolved(conn):
    wid = _ws(conn, "SZN UNK")
    comp = competitions.create_competition(conn, wid, ACTOR, name="Mystery")   # season_model defaults to 'unknown'
    mid = _match(conn, wid, comp, date(2020, 1, 15))
    out = seasons.auto_assign_season(conn, wid, ACTOR, mid)
    assert out["applied"] is False
    assert matches.get_match(conn, mid)["season_id"] is None
    assert any("season_unresolved" in w for w in seasons.season_warnings(conn, mid))   # flagged, not guessed


def test_manual_season_is_preserved(conn):
    wid = _ws(conn, "SZN MANUAL")
    comp = competitions.create_competition(conn, wid, ACTOR, name="League", season_model="au_summer")
    sid = competitions.create_season(conn, wid, ACTOR, comp, label="Manual Season")
    mid = _match(conn, wid, comp, date(2020, 2, 1))
    matches.update_match(conn, wid, ACTOR, mid, season_id=sid)          # manual choice
    assert matches.get_match(conn, mid)["season_source"] == "manual"
    out = seasons.auto_assign_season(conn, wid, ACTOR, mid)
    assert out["applied"] is False and matches.get_match(conn, mid)["season_id"] == sid  # preserved


def test_idempotent(conn):
    wid = _ws(conn, "SZN IDEM")
    comp = competitions.create_competition(conn, wid, ACTOR, name="League", season_model="calendar")
    mid = _match(conn, wid, comp, date(2021, 3, 1))
    seasons.auto_assign_season(conn, wid, ACTOR, mid)
    before = matches.get_match(conn, mid)["season_id"]
    assert seasons.auto_assign_season(conn, wid, ACTOR, mid)["applied"] is False   # no change
    assert matches.get_match(conn, mid)["season_id"] == before
    assert conn.execute(text("SELECT count(*) FROM season WHERE competition_id = :c"), {"c": comp}).scalar_one() == 1
