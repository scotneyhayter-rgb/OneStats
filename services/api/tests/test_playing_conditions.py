"""Live playing-conditions tests (Phase 4, Stage 4).

Rolled back in a single transaction (no data persists); skipped without a live DB. Runs as the
least-privilege ``onestats_app`` role under FORCE RLS. Covers configuration at each scope, the
match → grade → season → competition resolution order, unknown-stays-unknown semantics, the
configurable (never hard-coded) team-size limit, era-specific rules not leaking across seasons,
competition points, workspace isolation, permissions, audit and invalid inputs.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import competitions, permissions, playing_conditions

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


def _mk_user(conn, username):
    return conn.execute(
        text("INSERT INTO app_user(username) VALUES (:u) RETURNING id"), {"u": username}
    ).scalar_one()


def _ws(conn, name):
    wid = _mk_workspace(conn, name)
    set_workspace(conn, wid)
    return wid


def _comp(conn, wid, name="League"):
    return competitions.create_competition(conn, wid, ACTOR, name=name)


# ------------------------------------------------------------ configuration


def test_set_and_get_conditions_at_each_scope(conn):
    wid = _ws(conn, "PC WS1")
    cid = _comp(conn, wid)
    grade = competitions.create_grade(conn, wid, ACTOR, cid, name="A Grade")
    season = competitions.create_season(conn, wid, ACTOR, cid, label="2025/26")

    playing_conditions.set_conditions(conn, wid, ACTOR, scope="competition", target_id=cid,
                                      balls_per_over=6, format="two_day")
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="grade", target_id=grade, overs_limit=80)
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="season", target_id=season, max_players=11)

    assert playing_conditions.get_for_scope(conn, "competition", cid)["balls_per_over"] == 6
    assert playing_conditions.get_for_scope(conn, "grade", grade)["overs_limit"] == 80
    assert playing_conditions.get_for_scope(conn, "season", season)["max_players"] == 11


def test_upsert_is_idempotent_per_scope_target(conn):
    wid = _ws(conn, "PC WS2")
    cid = _comp(conn, wid)
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="competition", target_id=cid, overs_limit=50)
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="competition", target_id=cid, balls_per_over=8)
    rows = playing_conditions.list_conditions(conn, competition_id=cid)
    assert len(rows) == 1  # one row per scope target
    row = playing_conditions.get_for_scope(conn, "competition", cid)
    assert row["overs_limit"] == 50 and row["balls_per_over"] == 8  # update merged, nothing wiped


# ------------------------------------------------------------ resolution order


def test_resolution_prefers_more_specific_scope(conn):
    wid = _ws(conn, "PC WS3")
    cid = _comp(conn, wid)
    grade = competitions.create_grade(conn, wid, ACTOR, cid, name="A")
    season = competitions.create_season(conn, wid, ACTOR, cid, label="2025/26")
    # competition sets a baseline; grade overrides overs_limit; season sets balls_per_over.
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="competition", target_id=cid,
                                      overs_limit=40, balls_per_over=6, max_players=11)
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="grade", target_id=grade, overs_limit=50)
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="season", target_id=season, balls_per_over=8)

    eff = playing_conditions.resolve_effective(conn, competition_id=cid, season_id=season, grade_id=grade)
    c = eff["conditions"]
    assert c["overs_limit"] == 50  # grade wins over competition
    assert c["balls_per_over"] == 8  # season wins over competition
    assert c["max_players"] == 11  # only competition set it -> inherited
    assert eff["sources"]["overs_limit"] == "grade"
    assert eff["sources"]["balls_per_over"] == "season"
    assert eff["sources"]["max_players"] == "competition"


def test_match_scope_has_highest_priority(conn):
    wid = _ws(conn, "PC WS3b")
    cid = _comp(conn, wid)
    grade = competitions.create_grade(conn, wid, ACTOR, cid, name="A")
    # Phase 6 resolved the match_id FK, so a match-scoped condition needs a real match.
    match_id = conn.execute(
        text("INSERT INTO match(workspace_id, competition_id, grade_id) VALUES (:w, :c, :g) RETURNING id"),
        {"w": wid, "c": cid, "g": grade},
    ).scalar_one()
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="grade", target_id=grade, overs_limit=50)
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="match", target_id=match_id, overs_limit=20)
    eff = playing_conditions.resolve_effective(conn, competition_id=cid, grade_id=grade, match_id=match_id)
    assert eff["conditions"]["overs_limit"] == 20
    assert eff["sources"]["overs_limit"] == "match"


def test_unknown_stays_unknown(conn):
    wid = _ws(conn, "PC WS4")
    cid = _comp(conn, wid)
    # Only balls_per_over is recorded; everything else must remain None (not defaulted).
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="competition", target_id=cid, balls_per_over=6)
    eff = playing_conditions.resolve_effective(conn, competition_id=cid)
    c = eff["conditions"]
    assert c["balls_per_over"] == 6
    assert c["overs_limit"] is None
    assert c["max_players"] is None
    assert c["innings_per_side"] is None
    assert c["format"] is None


# ------------------------------------------------------------ configurable team size


def test_team_size_is_configurable_not_hardcoded(conn):
    """A junior grade can be given max_players=15, but it is configured, never defaulted."""
    wid = _ws(conn, "PC WS5")
    cid = _comp(conn, wid)
    junior = competitions.create_grade(conn, wid, ACTOR, cid, name="Under 14", program="junior_girls")
    senior = competitions.create_grade(conn, wid, ACTOR, cid, name="A Grade", program="senior_mens")
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="grade", target_id=junior, max_players=15)
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="grade", target_id=senior, max_players=11)
    assert playing_conditions.resolve_effective(conn, competition_id=cid, grade_id=junior)["conditions"]["max_players"] == 15
    assert playing_conditions.resolve_effective(conn, competition_id=cid, grade_id=senior)["conditions"]["max_players"] == 11
    # A grade with no condition set has unknown team size (not an implicit 15).
    bare = competitions.create_grade(conn, wid, ACTOR, cid, name="B Grade")
    assert playing_conditions.resolve_effective(conn, competition_id=cid, grade_id=bare)["conditions"]["max_players"] is None


# ------------------------------------------------------------ era-specific rules


def test_historical_rules_do_not_leak_across_seasons(conn):
    wid = _ws(conn, "PC WS6")
    cid = _comp(conn, wid)
    old = competitions.create_season(conn, wid, ACTOR, cid, label="1996/97")
    new = competitions.create_season(conn, wid, ACTOR, cid, label="2025/26")
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="season", target_id=old, balls_per_over=8)
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="season", target_id=new, balls_per_over=6)
    assert playing_conditions.resolve_effective(conn, competition_id=cid, season_id=old)["conditions"]["balls_per_over"] == 8
    assert playing_conditions.resolve_effective(conn, competition_id=cid, season_id=new)["conditions"]["balls_per_over"] == 6


# ------------------------------------------------------------ competition points


def test_points_scheme_stored_and_resolved(conn):
    wid = _ws(conn, "PC WS7")
    cid = _comp(conn, wid)
    scheme = {"win": 6, "tie": 3, "draw": 1, "loss": 0, "bonus_batting": True}
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="competition", target_id=cid, points=scheme)
    eff = playing_conditions.resolve_effective(conn, competition_id=cid)
    assert eff["conditions"]["points"] == scheme
    assert eff["sources"]["points"] == "competition"


def test_clear_conditions(conn):
    wid = _ws(conn, "PC WS8")
    cid = _comp(conn, wid)
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="competition", target_id=cid, overs_limit=45)
    assert playing_conditions.clear_conditions(conn, wid, ACTOR, scope="competition", target_id=cid) is True
    assert playing_conditions.get_for_scope(conn, "competition", cid) is None
    assert playing_conditions.resolve_effective(conn, competition_id=cid)["conditions"]["overs_limit"] is None


# ------------------------------------------------------------ isolation


def test_conditions_isolated_across_workspaces(conn):
    wid_a = _mk_workspace(conn, "PC ISO A")
    wid_b = _mk_workspace(conn, "PC ISO B")
    set_workspace(conn, wid_a)
    cid_a = _comp(conn, wid_a, "A League")
    playing_conditions.set_conditions(conn, wid_a, ACTOR, scope="competition", target_id=cid_a, overs_limit=50)
    set_workspace(conn, wid_b)
    # Competition A is invisible here, and its conditions do not resolve.
    assert playing_conditions.get_for_scope(conn, "competition", cid_a) is None
    assert playing_conditions.resolve_effective(conn, competition_id=cid_a)["conditions"]["overs_limit"] is None


# ------------------------------------------------------------ permissions


def test_competition_manage_governs_playing_conditions(conn):
    wid = _ws(conn, "PC PERM WS")
    admin = _mk_user(conn, "pc_admin")
    viewer = _mk_user(conn, "pc_viewer")
    permissions.grant_role(conn, admin, wid, "workspace_admin")
    permissions.grant_role(conn, viewer, wid, "viewer")
    assert "competition.manage" in permissions.effective_permissions(conn, admin, wid, False)
    assert "competition.manage" not in permissions.effective_permissions(conn, viewer, wid, False)


# ------------------------------------------------------------ audit


def test_condition_changes_are_audited(conn):
    wid = _ws(conn, "PC AUDIT WS")
    cid = _comp(conn, wid)
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="competition", target_id=cid, overs_limit=50)
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="competition", target_id=cid, overs_limit=40)
    playing_conditions.clear_conditions(conn, wid, ACTOR, scope="competition", target_id=cid)
    actions = conn.execute(
        text("SELECT action FROM audit_log WHERE action LIKE 'playing_condition%'")
    ).scalars().all()
    for expected in ("playing_condition.create", "playing_condition.update", "playing_condition.delete"):
        assert expected in actions


# ------------------------------------------------------------ invalid inputs


def test_invalid_inputs(conn):
    wid = _ws(conn, "PC INVALID WS")
    with pytest.raises(ValueError, match="invalid_scope"):
        playing_conditions.set_conditions(conn, wid, ACTOR, scope="banana", target_id=uuid.uuid4())
    with pytest.raises(ValueError, match="grade_not_found"):
        playing_conditions.set_conditions(conn, wid, ACTOR, scope="grade", target_id=uuid.uuid4(), overs_limit=40)
