"""Live innings & extras tests (Phase 6, Stage 2).

Rolled back in a single transaction (no data persists); skipped without a live DB. Runs as the
least-privilege ``onestats_app`` role under FORCE RLS. Covers multiple innings, team validation,
all five extras with unknown-aware totals, the official override (kept distinct from source),
status (declared/closed/forfeited/incomplete), non-blocking validation, isolation, permissions,
audit and invalid inputs.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import competitions, matches, permissions
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


def _match_with_teams(conn, wid):
    cid = competitions.create_competition(conn, wid, ACTOR, name="League")
    org = _org(conn, wid, "Club")
    home = _team(conn, wid, org, "Home")
    away = _team(conn, wid, org, "Away")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=cid)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    return mid, home, away


def test_multiple_innings_with_teams(conn):
    wid = _ws(conn, "INN WS1")
    mid, home, away = _match_with_teams(conn, wid)
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home,
                            bowling_team_id=away, status="completed")
    i2 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=2, batting_team_id=away,
                            bowling_team_id=home, status="completed")
    rows = inn.list_innings(conn, mid)
    assert [r["inns_number"] for r in rows] == [1, 2]
    assert inn.get_innings(conn, i1)["batting_team_id"] == home
    assert i2 in {r["id"] for r in rows}
    # a batting team must be a side of the match
    with pytest.raises(ValueError, match="team_not_in_match"):
        inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=3, batting_team_id=uuid.uuid4())


def test_extras_unknown_aware_totals(conn):
    wid = _ws(conn, "INN WS2")
    mid, home, away = _match_with_teams(conn, wid)
    i = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home,
                           bowling_team_id=away, byes=4, legbyes=2, wides=3)  # noballs/penalty unknown
    t = inn.totals(conn, i)
    assert t["extras_total"] == 9  # 4+2+3 (unknown noballs/penalty excluded, not treated as 0)
    assert t["batting_runs"] is None   # batting card not entered yet -> unknown, not 0
    assert t["derived_total"] is None  # unknown until batting exists
    # an innings with no extras recorded at all -> extras_total unknown (None), never 0
    i2 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=2, batting_team_id=away, bowling_team_id=home)
    assert inn.totals(conn, i2)["extras_total"] is None


def test_official_override_kept_distinct(conn):
    wid = _ws(conn, "INN WS3")
    mid, home, away = _match_with_teams(conn, wid)
    i = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home,
                           bowling_team_id=away, byes=5)
    inn.set_official_total(conn, wid, ACTOR, i, total=162, wickets=8, reason="scorebook",
                           evidence="RMCC 2026 scorebook p.4")
    row = inn.get_innings(conn, i)
    assert row["official_total"] == 162 and row["official_wickets"] == 8
    assert row["override_reason"] == "scorebook" and row["override_by"] == ACTOR
    assert row["byes"] == 5  # source extras untouched
    assert inn.totals(conn, i)["official_total"] == 162


def test_statuses_and_iresult_preserved(conn):
    wid = _ws(conn, "INN WS4")
    mid, home, away = _match_with_teams(conn, wid)
    for n, st in ((1, "declared"), (2, "forfeited"), (3, "incomplete")):
        i = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=n, batting_team_id=home,
                               bowling_team_id=away, status=st, iresult_raw="2")
        row = inn.get_innings(conn, i)
        assert row["status"] == st
        assert row["iresult_raw"] == "2" and row["iresult_status"] == "unresolved"  # mapping not guessed


def test_validation_is_non_blocking(conn):
    wid = _ws(conn, "INN WS5")
    mid, home, away = _match_with_teams(conn, wid)
    # incomplete innings with unknown teams still SAVES, and surfaces warnings
    i = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, status="incomplete")
    assert inn.get_innings(conn, i) is not None
    w = inn.validation_warnings(conn, i)
    assert "innings_teams_unknown" in w
    # an official total below the known extras is flagged, not rejected
    i2 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=2, batting_team_id=home,
                            bowling_team_id=away, byes=20)
    inn.set_official_total(conn, wid, ACTOR, i2, total=10)
    assert "official_total_less_than_extras" in inn.validation_warnings(conn, i2)


def test_isolation(conn):
    wid_a = _mk_workspace(conn, "INN ISO A")
    wid_b = _mk_workspace(conn, "INN ISO B")
    set_workspace(conn, wid_a)
    mid, home, away = _match_with_teams(conn, wid_a)
    i = inn.create_innings(conn, wid_a, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    set_workspace(conn, wid_b)
    assert inn.get_innings(conn, i) is None
    assert inn.list_innings(conn, mid) == []


def test_permission_and_audit(conn):
    wid = _ws(conn, "INN PERM")
    admin = _mk_user(conn, "inn_admin")
    viewer = _mk_user(conn, "inn_viewer")
    permissions.grant_role(conn, admin, wid, "workspace_admin")
    permissions.grant_role(conn, viewer, wid, "viewer")
    assert "match.manage" in permissions.effective_permissions(conn, admin, wid, False)
    assert "match.manage" not in permissions.effective_permissions(conn, viewer, wid, False)

    mid, home, away = _match_with_teams(conn, wid)
    i = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    inn.update_innings(conn, wid, ACTOR, i, byes=3)
    inn.set_official_total(conn, wid, ACTOR, i, total=100)
    actions = conn.execute(text("SELECT action FROM audit_log WHERE action LIKE 'innings%'")).scalars().all()
    for expected in ("innings.create", "innings.update", "innings.official_override"):
        assert expected in actions


def test_invalid_inputs(conn):
    wid = _ws(conn, "INN INVALID")
    with pytest.raises(ValueError, match="match_not_found"):
        inn.create_innings(conn, wid, ACTOR, match_id=uuid.uuid4(), inns_number=1)
    mid, home, _away = _match_with_teams(conn, wid)
    with pytest.raises(ValueError, match="invalid_status"):
        inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, status="banana")
    with pytest.raises(ValueError, match="teams_must_differ"):
        inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=2, batting_team_id=home, bowling_team_id=home)
