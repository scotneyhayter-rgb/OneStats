"""Live batting & dismissal tests (Phase 6, Stage 3).

Rolled back in a single transaction (no data persists); skipped without a live DB. Runs as the
least-privilege ``onestats_app`` role under FORCE RLS. Covers batting order & identity, runs/balls/
boundaries, the full dismissal taxonomy with bowler/fielder attribution, preserved source codes,
unknown-vs-zero, incomplete/newspaper cards, non-blocking validation, duplicate protection,
isolation, permissions, audit and invalid inputs.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import batting as bat
from onestats.domain import competitions, matches, people, permissions
from onestats.domain import innings as inn

settings = get_settings()
pytestmark = pytest.mark.skipif(
    not settings.db_configured, reason="no live database credential configured"
)

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


def _mk_workspace(conn, name):
    return conn.execute(
        text("INSERT INTO workspace(name, type) VALUES (:n,'club') RETURNING id"), {"n": name}
    ).scalar_one()


def _mk_user(conn, u):
    return conn.execute(text("INSERT INTO app_user(username) VALUES (:u) RETURNING id"), {"u": u}).scalar_one()


def _ws(conn, name):
    wid = _mk_workspace(conn, name)
    set_workspace(conn, wid)
    return wid


def _org(conn, wid, name):
    return conn.execute(
        text("INSERT INTO organisation(workspace_id, name, kind) VALUES (:w, :n, 'club') RETURNING id"),
        {"w": wid, "n": name},
    ).scalar_one()


def _team(conn, wid, org, name):
    return conn.execute(
        text("INSERT INTO team(workspace_id, organisation_id, name) VALUES (:w, :o, :n) RETURNING id"),
        {"w": wid, "o": org, "n": name},
    ).scalar_one()


def _innings(conn, wid):
    cid = competitions.create_competition(conn, wid, ACTOR, name="League")
    org = _org(conn, wid, "Club")
    home = _team(conn, wid, org, "Home")
    away = _team(conn, wid, org, "Away")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=cid)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    iid = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1,
                             batting_team_id=home, bowling_team_id=away)
    return iid


def _person(conn, wid, name):
    return people.create_person(conn, wid, ACTOR, display_name=name)


def test_order_identity_and_stats(conn):
    wid = _ws(conn, "BAT WS1")
    iid = _innings(conn, wid)
    p1 = _person(conn, wid, "Opener One")
    p2 = _person(conn, wid, "Opener Two")
    bat.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=p2, batting_position=2,
                     runs=34, balls_faced=50, fours=4, sixes=1, dismissal_type="bowled",
                     dismissal_source_code="2")
    bat.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=p1, batting_position=1,
                     runs=12, dismissal_type="lbw", dismissal_source_code="6")
    rows = bat.list_entries(conn, iid)
    assert [r["batting_position"] for r in rows] == [1, 2]  # ordered by position
    assert rows[1]["runs"] == 34 and rows[1]["fours"] == 4
    card = bat.batting_card(conn, iid)
    assert card["runs_total"] == 46 and card["wickets"] == 2 and card["batted"] == 2


def test_dismissal_taxonomy_and_attribution(conn):
    wid = _ws(conn, "BAT WS2")
    iid = _innings(conn, wid)
    bowler = _person(conn, wid, "The Bowler")
    fielder = _person(conn, wid, "The Fielder")
    caught = bat.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=_person(conn, wid, "Caught"),
                              batting_position=1, runs=10, dismissal_type="caught",
                              dismissal_source_code="3", bowler_person_id=bowler, fielder_person_id=fielder)
    runout = bat.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=_person(conn, wid, "RunOut"),
                              batting_position=2, runs=5, dismissal_type="run_out",
                              dismissal_source_code="7", fielder_person_id=fielder)
    assert bat.get_entry(conn, caught)["bowler_person_id"] == bowler
    assert bat.get_entry(conn, caught)["fielder_person_id"] == fielder
    # run_out has a fielder but credits no bowler
    assert bat.get_entry(conn, runout)["bowler_person_id"] is None
    assert bat.get_entry(conn, runout)["dismissal_source_code"] == "7"


def test_not_out_dnb_and_wicket_counting(conn):
    wid = _ws(conn, "BAT WS3")
    iid = _innings(conn, wid)
    bat.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=_person(conn, wid, "A"),
                     batting_position=1, runs=50, dismissal_type="not_out")
    bat.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=_person(conn, wid, "B"),
                     batting_position=2, runs=20, dismissal_type="caught")
    bat.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=_person(conn, wid, "C"),
                     batting_position=3, dismissal_type="dnb")  # no innings — not counted
    bat.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=_person(conn, wid, "D"),
                     batting_position=4, runs=0, dismissal_type="unknown_out")  # out, manner unknown -> wicket
    card = bat.batting_card(conn, iid)
    assert card["wickets"] == 2            # caught + unknown_out (not_out & dnb excluded)
    assert card["batted"] == 3             # dnb excluded
    assert card["runs_total"] == 70        # 50 + 20 + 0 (D's 0 is a real zero)


def test_unknown_is_not_zero(conn):
    wid = _ws(conn, "BAT WS4")
    iid = _innings(conn, wid)
    # a newspaper card: batter known, runs unknown (balls never recorded historically)
    bat.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=_person(conn, wid, "X"),
                     batting_position=1, dismissal_type="caught", evidence="The Argus, 12 Jan 1962")
    card = bat.batting_card(conn, iid)
    assert card["runs_total"] is None      # unknown, NOT 0
    assert card["balls_total"] is None
    assert card["wickets"] == 1
    # derived innings total stays unknown when batting runs are unknown (Stage 2 contract)
    assert inn.totals(conn, iid)["batting_runs"] is None
    assert inn.totals(conn, iid)["derived_wickets"] == 1


def test_source_code_preserved_and_unresolved_flagged(conn):
    wid = _ws(conn, "BAT WS5")
    iid = _innings(conn, wid)
    # an unconfirmed CS code mapped to the unresolved bucket — original code kept verbatim
    e = bat.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=_person(conn, wid, "Y"),
                         batting_position=1, dismissal_type="unknown", dismissal_source_code="24")
    assert bat.get_entry(conn, e)["dismissal_source_code"] == "24"
    assert "dismissal_unresolved" in bat.validation_warnings(conn, iid)


def test_validation_non_blocking(conn):
    wid = _ws(conn, "BAT WS6")
    iid = _innings(conn, wid)
    bowler = _person(conn, wid, "B")
    # a bowler attributed to a run-out saves, but is flagged
    bat.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=_person(conn, wid, "Z"),
                     batting_position=1, dismissal_type="run_out", bowler_person_id=bowler)
    assert bat.list_entries(conn, iid)[0]["bowler_person_id"] == bowler  # saved
    assert "bowler_on_non_bowler_dismissal" in bat.validation_warnings(conn, iid)


def test_duplicate_protection(conn):
    wid = _ws(conn, "BAT WS7")
    iid = _innings(conn, wid)
    p = _person(conn, wid, "Solo")
    bat.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=p, batting_position=1)
    with pytest.raises(ValueError, match="duplicate_batter"):
        bat.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=p, batting_position=2)
    with pytest.raises(ValueError, match="duplicate_position"):
        bat.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=_person(conn, wid, "Other"),
                         batting_position=1)


def test_isolation(conn):
    wid_a = _mk_workspace(conn, "BAT ISO A")
    wid_b = _mk_workspace(conn, "BAT ISO B")
    set_workspace(conn, wid_a)
    iid = _innings(conn, wid_a)
    e = bat.create_entry(conn, wid_a, ACTOR, innings_id=iid, person_id=_person(conn, wid_a, "H"),
                         batting_position=1, runs=1)
    set_workspace(conn, wid_b)
    assert bat.get_entry(conn, e) is None
    assert bat.list_entries(conn, iid) == []


def test_permission_and_audit(conn):
    wid = _ws(conn, "BAT PERM")
    admin = _mk_user(conn, "bat_admin")
    viewer = _mk_user(conn, "bat_viewer")
    permissions.grant_role(conn, admin, wid, "workspace_admin")
    permissions.grant_role(conn, viewer, wid, "viewer")
    assert "match.manage" in permissions.effective_permissions(conn, admin, wid, False)
    assert "match.manage" not in permissions.effective_permissions(conn, viewer, wid, False)

    iid = _innings(conn, wid)
    e = bat.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=_person(conn, wid, "P"),
                         batting_position=1, runs=3)
    bat.update_entry(conn, wid, ACTOR, e, runs=4)
    bat.delete_entry(conn, wid, ACTOR, e)
    actions = conn.execute(text("SELECT action FROM audit_log WHERE action LIKE 'batting_entry%'")).scalars().all()
    for expected in ("batting_entry.create", "batting_entry.update", "batting_entry.delete"):
        assert expected in actions


def test_invalid_inputs(conn):
    wid = _ws(conn, "BAT INVALID")
    with pytest.raises(ValueError, match="innings_not_found"):
        bat.create_entry(conn, wid, ACTOR, innings_id=uuid.uuid4(), batting_position=1)
    iid = _innings(conn, wid)
    with pytest.raises(ValueError, match="invalid_dismissal_type"):
        bat.create_entry(conn, wid, ACTOR, innings_id=iid, batting_position=1, dismissal_type="skied_it")
