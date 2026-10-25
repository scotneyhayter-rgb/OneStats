"""Phase 13, Stages 13.16/13.17 — Club Record Book PDF (shared framework). Rolled back; skipped w/o DB."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import Settings, get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import batting, competitions, matches, people
from onestats.domain import innings as inn
from onestats.domain.records import honours
from onestats.reports import record_book

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
    conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a, :u) ON CONFLICT (id) DO NOTHING"),
                 {"a": ACTOR, "u": f"actor-{name}"})
    set_workspace(conn, wid)
    return wid


def _team(conn, wid, name):
    org = conn.execute(text("INSERT INTO organisation(workspace_id,name,kind) VALUES (:w,:n,'club') RETURNING id"),
                       {"w": wid, "n": name + " CC"}).scalar_one()
    return conn.execute(text("INSERT INTO team(workspace_id,organisation_id,name) VALUES (:w,:o,:n) RETURNING id"),
                        {"w": wid, "o": org, "n": name}).scalar_one()


def test_record_book_pdf(conn):
    wid = _ws(conn, "BOOK")
    comp = competitions.create_competition(conn, wid, ACTOR, name="L")
    home, away = _team(conn, wid, "H"), _team(conn, wid, "A")
    p = people.create_person(conn, wid, ACTOR, display_name="Record Holder")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=comp)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=p, batting_position=1,
                         runs=200, balls_faced=180, dismissal_type="not_out")
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    honours.create_honour(conn, wid, ACTOR, honour_type="life_member", title="Life Member", person_id=p)

    pdf = record_book.record_book_pdf(conn, Settings(env="test", db_password=None, _env_file=None), wid)
    assert pdf[:5] == b"%PDF-" and len(pdf) > 3000 and b"/Page" in pdf


def test_record_book_empty_workspace(conn):
    wid = _ws(conn, "BOOK EMPTY")
    pdf = record_book.record_book_pdf(conn, Settings(env="test", db_password=None, _env_file=None), wid)
    assert pdf[:5] == b"%PDF-"   # graceful empty book, not a crash
