"""Website publishing (Phase 15) — hosting-neutral: publish a report/profile, serve the snapshot publicly
with no workspace context (offline-capable), privacy-filter profiles, publish/unpublish/revoke, static
export, automatic-staleness on stat change, and workspace isolation. Requires a live DB; rolled back.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import Settings, get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import batting, competitions, matches, people, publishing
from onestats.domain import innings as inn

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
ACTOR = "11111111-1111-1111-1111-111111111111"
TS = Settings(env="test", db_password=None, _env_file=None)


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
    conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a, 'pub') ON CONFLICT (id) DO NOTHING"), {"a": ACTOR})
    set_workspace(conn, wid)
    return wid


def _team(conn, wid, name):
    org = conn.execute(text("INSERT INTO organisation(workspace_id,name,kind) VALUES (:w,:n,'club') RETURNING id"),
                       {"w": wid, "n": name + " CC"}).scalar_one()
    return conn.execute(text("INSERT INTO team(workspace_id,organisation_id,name) VALUES (:w,:o,:n) RETURNING id"),
                        {"w": wid, "o": org, "n": name}).scalar_one()


def _match(conn, wid, comp, se, home, away, p, runs):
    mid = matches.create_match(conn, wid, ACTOR, competition_id=comp, season_id=se)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    batting.create_entry(conn, wid, ACTOR, innings_id=i1, person_id=p, batting_position=1, runs=runs, dismissal_type="bowled")
    matches.set_result(conn, wid, ACTOR, mid, result_type="home_win", won_by_team_id=home)
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    return mid


def _no_context(conn):
    """Clear the workspace GUC to emulate the public (unauthenticated) read path."""
    conn.execute(text("SELECT set_config('onestats.workspace_id', '', true)"))


@pytest.fixture
def seeded(conn):
    wid = _ws(conn, "PUB")
    comp = competitions.create_competition(conn, wid, ACTOR, name="League")
    se = conn.execute(text("INSERT INTO season(workspace_id,competition_id,label,start_date) "
                           "VALUES (:w,:c,'2024/25','2024-10-01') RETURNING id"), {"w": wid, "c": comp}).scalar_one()
    home, away = _team(conn, wid, "Rhymney"), _team(conn, wid, "Away")
    p = people.create_person(conn, wid, ACTOR, display_name="Star Player")
    _match(conn, wid, comp, se, home, away, p, 100)
    return {"wid": wid, "comp": comp, "se": se, "home": home, "away": away, "p": p}


def test_publish_report_and_serve_public(seeded, conn):
    wid = seeded["wid"]
    pub = publishing.create_publication(conn, TS, wid, ACTOR, kind="report", title="Leading Run Scorers",
                                        report_id="bat_most_runs")
    assert pub["slug"] and pub["status"] == "published" and pub["snapshot"] is not None
    # public read with NO workspace context resolves the snapshot by slug
    _no_context(conn)
    got = publishing.get_public(conn, pub["slug"])
    assert got is not None and got["kind"] == "report"
    rows = got["snapshot"]["rows"] if isinstance(got["snapshot"], dict) else json.loads(got["snapshot"])["rows"]
    assert rows[0]["player"] == "Star Player" and rows[0]["runs"] == 100


def test_unpublish_and_revoke_stop_serving(seeded, conn):
    wid = seeded["wid"]
    pub = publishing.create_publication(conn, TS, wid, ACTOR, kind="report", title="R", report_id="bat_most_runs")
    slug = pub["slug"]
    publishing.set_status(conn, wid, ACTOR, pub["id"], "unpublished")
    _no_context(conn); assert publishing.get_public(conn, slug) is None
    set_workspace(conn, wid)
    publishing.set_status(conn, wid, ACTOR, pub["id"], "published")
    _no_context(conn); assert publishing.get_public(conn, slug) is not None
    set_workspace(conn, wid)
    publishing.set_status(conn, wid, ACTOR, pub["id"], "revoked")
    _no_context(conn); assert publishing.get_public(conn, slug) is None


def test_offline_last_good_snapshot_and_stale_refresh(seeded, conn):
    """A stat change marks the publication stale but the public snapshot keeps serving the last good copy
    until a refresh regenerates it (offline-capable, never goes dark)."""
    d = seeded
    wid = d["wid"]
    pub = publishing.create_publication(conn, TS, wid, ACTOR, kind="report", title="R", report_id="bat_most_runs")
    slug = pub["slug"]
    # approve another match → the player now has 150, and publications are flagged stale
    _match(conn, wid, d["comp"], d["se"], d["home"], d["away"], d["p"], 50)
    stale = conn.execute(text("SELECT stale FROM publication WHERE id = :i"), {"i": pub["id"]}).scalar_one()
    assert stale is True
    # public still serves the LAST good snapshot (100), not the new total
    _no_context(conn)
    rows = publishing.get_public(conn, slug)["snapshot"]["rows"]
    assert rows[0]["runs"] == 100
    # refresh regenerates; now public serves 150 and stale is cleared
    set_workspace(conn, wid)
    assert publishing.refresh_workspace(conn, TS, wid, ACTOR)["refreshed"] == 1
    assert conn.execute(text("SELECT stale FROM publication WHERE id = :i"), {"i": pub["id"]}).scalar_one() is False
    _no_context(conn)
    assert publishing.get_public(conn, slug)["snapshot"]["rows"][0]["runs"] == 150


def test_static_export_files(seeded, conn):
    wid = seeded["wid"]
    pub = publishing.create_publication(conn, TS, wid, ACTOR, kind="report", title="Leading Run Scorers",
                                        report_id="bat_most_runs")
    files = publishing.static_export(conn, wid, pub["id"])
    html = files[f"{pub['slug']}.html"]
    assert f"{pub['slug']}.json" in files and f"{pub['slug']}.html" in files
    assert "<table" in html and "Star Player" in html and "PUB" in html   # table + club header
    assert json.loads(files[f"{pub['slug']}.json"])["title"] == "Leading Run Scorers"


def test_public_profile_excludes_private_data(seeded, conn):
    wid, p = seeded["wid"], seeded["p"]
    # give the person a date of birth (private) — it must never appear in the public snapshot
    conn.execute(text("UPDATE person SET dob = '1990-01-01', dob_precision = 'exact' WHERE id = :p"), {"p": p})
    pub = publishing.create_publication(conn, TS, wid, ACTOR, kind="player_profile", title="Star Player", person_id=p)
    _no_context(conn)
    got = publishing.get_public(conn, pub["slug"])
    blob = json.dumps(got["snapshot"] if isinstance(got["snapshot"], dict) else json.loads(got["snapshot"]))
    assert got["kind"] == "player_profile" and "Star Player" in blob
    assert "1990-01-01" not in blob               # the private DOB is never published


def test_isolation_admin_cannot_see_other_workspace(seeded, conn):
    wid = seeded["wid"]
    pub = publishing.create_publication(conn, TS, wid, ACTOR, kind="report", title="R", report_id="bat_most_runs")
    other = _ws(conn, "PUB OTHER")                     # switches workspace context to the other workspace
    assert publishing.list_publications(conn, other) == []   # admin of B sees none of A's
    # but the public edge (no context) can still serve A's published snapshot (intended)
    _no_context(conn)
    assert publishing.get_public(conn, pub["slug"]) is not None
