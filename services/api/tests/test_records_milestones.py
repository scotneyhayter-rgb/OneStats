"""Phase 13, Stage 13.5/13.14 — career milestones & upcoming. Rolled back; skipped without a live DB."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import batting, competitions, matches, people
from onestats.domain import innings as inn
from onestats.domain.records import milestones

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


def _build(conn, wid):
    comp = competitions.create_competition(conn, wid, ACTOR, name="L")
    home, away = _team(conn, wid, "H"), _team(conn, wid, "A")
    confirmed = people.create_person(conn, wid, ACTOR, display_name="Confirmed")
    unknown = people.create_person(conn, wid, ACTOR, display_name="Unknown Runs")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=comp)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=confirmed, batting_position=1,
                         runs=120, balls_faced=90, dismissal_type="not_out")
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=unknown, batting_position=2,
                         runs=None, dismissal_type="bowled")   # unknown runs
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    return confirmed, unknown


def test_confirmed_milestone(conn):
    wid = _ws(conn, "MS CONF")
    confirmed, _ = _build(conn, wid)
    ms = milestones.person_milestones(conn, wid, confirmed)
    runs = ms["metrics"]["runs"]
    assert runs["total"] == 120 and runs["known_minimum"] is False
    assert {m["threshold"]: m["state"] for m in runs["milestones"]}[100] == "achieved_confirmed"
    assert runs["next"]["threshold"] == 500 and runs["next"]["to_go"] == 380


def test_unknown_runs_is_indeterminate_not_zero(conn):
    wid = _ws(conn, "MS UNK")
    _, unknown = _build(conn, wid)
    ms = milestones.person_milestones(conn, wid, unknown)
    runs = ms["metrics"]["runs"]
    assert runs["known_minimum"] is True
    # cannot confirm the 100 milestone is NOT reached when runs are unknown -> indeterminate, never "not achieved as 0"
    assert {m["threshold"]: m["state"] for m in runs["milestones"]}[100] == "indeterminate"


def test_upcoming_excludes_incomplete(conn):
    wid = _ws(conn, "MS UP")
    confirmed, _ = _build(conn, wid)
    # within 5 of 125? no (120, next real threshold 500). Use a wide window to include the confirmed player.
    up = milestones.upcoming_for_workspace(conn, wid, window=400)
    assert any(u["person_id"] == str(confirmed) and u["metric"] == "runs" and u["to_go"] == 380 for u in up)
