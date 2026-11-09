"""Phase 13, Stages 13.6/13.8 — honours (life members) + achievement badges.

Honours are explicitly recorded (never inferred); badges distinguish calculated statistical achievements
from awarded honours. Rolled back; skipped without a live DB.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import batting, competitions, matches, people, profiles
from onestats.domain import innings as inn
from onestats.domain.records import badges, honours

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


def test_honours_recorded_not_inferred(conn):
    wid = _ws(conn, "HON")
    p = people.create_person(conn, wid, ACTOR, display_name="Life Member")
    h = honours.create_honour(conn, wid, ACTOR, honour_type="life_member", title="Life Member 2005",
                              person_id=p, awarded_season="2004/05", evidence="Minutes of AGM")
    assert h["honour_type"] == "life_member" and h["status"] == "confirmed"
    assert len(honours.list_honours(conn, wid, person_id=p)) == 1
    with pytest.raises(ValueError, match="invalid_honour_type"):
        honours.create_honour(conn, wid, ACTOR, honour_type="knighthood", title="x")
    with pytest.raises(ValueError, match="title_required"):
        honours.create_honour(conn, wid, ACTOR, honour_type="club_award", title="  ")


def test_honorary_members_merges_honour_table_and_person_recognition(conn):
    """The Records 'Life Members & honorary recognition' list must show members recorded EITHER as a
    dedicated honour OR as a per-person recognition (what the People screen writes). Previously the
    recognition-based members were missing from the list entirely."""
    wid = _ws(conn, "HONMERGE")
    p1 = people.create_person(conn, wid, ACTOR, display_name="Alice Honour")
    p2 = people.create_person(conn, wid, ACTOR, display_name="Bob Recognition")
    honours.create_honour(conn, wid, ACTOR, honour_type="life_member", title="Life Member", person_id=p1)
    profiles.add_recognition(conn, wid, ACTOR, p2, recognition_type="Life Member", season_label="2019/20")

    members = honours.list_honorary_members(conn, wid)
    listed = {m["person"] for m in members}
    assert "Alice Honour" in listed
    assert "Bob Recognition" in listed          # the previously-missing recognition-based member now appears
    bob = next(m for m in members if m["person"] == "Bob Recognition")
    assert bob["honour_type"] == "life_member" and bob["source"] == "recognition"
    assert bob["awarded_season"] == "2019/20"


def test_honorary_members_does_not_double_count(conn):
    wid = _ws(conn, "HONDUP")
    p = people.create_person(conn, wid, ACTOR, display_name="Dup Member")
    honours.create_honour(conn, wid, ACTOR, honour_type="life_member", title="Life Member", person_id=p)
    profiles.add_recognition(conn, wid, ACTOR, p, recognition_type="Life Member")
    dup = [m for m in honours.list_honorary_members(conn, wid) if m["person"] == "Dup Member"]
    assert len(dup) == 1 and dup[0]["source"] == "honour"   # dedicated honour wins; not listed twice


def test_badges_distinguish_calculated_from_awarded(conn):
    wid = _ws(conn, "BADGE")
    comp = competitions.create_competition(conn, wid, ACTOR, name="L")
    home, away = _team(conn, wid, "H"), _team(conn, wid, "A")
    p = people.create_person(conn, wid, ACTOR, display_name="Allrounder")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=comp)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=p, batting_position=1,
                         runs=110, balls_faced=100, dismissal_type="not_out")
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    honours.create_honour(conn, wid, ACTOR, honour_type="life_member", title="Life Member", person_id=p)

    b = badges.person_badges(conn, wid, p)
    assert any("century" in x["label"].lower() and x["source"] == "calculated" for x in b["calculated"])
    assert any(x["source"] == "honorary" for x in b["awarded"])     # life member -> honorary, not calculated
    # 100-runs milestone is a calculated, confirmed badge
    assert any(x["source"] == "calculated" and x["state"] == "achieved_confirmed" for x in b["calculated"])
