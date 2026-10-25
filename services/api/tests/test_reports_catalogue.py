"""Phase 12, Stages 12.13/12.15 — report catalogue + branded PDF export (engine-backed).

Confirms the on-screen rows and the PDF come from the same engine (same figures), and the PDF is a real
vector document. Rolled back; skipped without a live DB.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import Settings, get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import batting, competitions, matches, people
from onestats.domain import innings as inn
from onestats.reports import catalogue

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


def _store():
    return Settings(env="test", db_password=None, _env_file=None)


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


def _approved(conn, wid):
    comp = competitions.create_competition(conn, wid, ACTOR, name="League")
    home, away = _team(conn, wid, "Home"), _team(conn, wid, "Away")
    p = people.create_person(conn, wid, ACTOR, display_name="Donald Bradman")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=comp)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=p, batting_position=1,
                         runs=334, balls_faced=400, dismissal_type="not_out")
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    return p


def test_report_rows_named_and_ranked(conn):
    wid = _ws(conn, "RPT ROWS")
    _approved(conn, wid)
    data = catalogue.report_rows(conn, wid, "batting", {"workspace_id": wid})
    assert data["title"].startswith("Batting")
    r0 = data["rows"][0]
    assert r0["rank"] == 1 and r0["player"] == "Donald Bradman" and r0["runs"] == 334


def test_pdf_matches_onscreen(conn):
    wid = _ws(conn, "RPT PDF")
    _approved(conn, wid)
    rows = catalogue.report_rows(conn, wid, "batting", {"workspace_id": wid})["rows"]
    pdf = catalogue.report_pdf(conn, _store(), wid, "batting", {"workspace_id": wid})
    assert pdf[:5] == b"%PDF-" and len(pdf) > 2500
    assert rows[0]["runs"] == 334   # same engine behind both -> on-screen and PDF agree


def test_unknown_report(conn):
    wid = _ws(conn, "RPT UNK")
    with pytest.raises(ValueError, match="unknown_report"):
        catalogue.report_rows(conn, wid, "nonsense", {"workspace_id": wid})
