"""Live match-core tests (Phase 6, Stage 1).

Rolled back in a single transaction (no data persists); skipped without a live DB. Runs as the
least-privilege ``onestats_app`` role under FORCE RLS. Covers match create/list/filter,
classification independent of round, result + margin, home/away teams with captain/keeper,
match-scope playing-condition resolution, the resolved finals-series/playing-condition FKs,
isolation, permissions, audit and invalid inputs.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import competitions, finals_series, matches, permissions, playing_conditions

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


def _person(conn, wid, name):
    from onestats.domain import people
    return people.create_person(conn, wid, ACTOR, display_name=name)


def _comp(conn, wid):
    return competitions.create_competition(conn, wid, ACTOR, name="League")


# ----------------------------------------------- create / classification independent of round


def test_create_match_classification_independent_of_round(conn):
    wid = _ws(conn, "MATCH WS1")
    cid = _comp(conn, wid)
    grade = competitions.create_grade(conn, wid, ACTOR, cid, name="A")
    season = competitions.create_season(conn, wid, ACTOR, cid, label="2025/26")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=cid, grade_id=grade, season_id=season,
                               match_date=date(2026, 3, 7), round="GF", matchtype="1 innings per side")
    m = matches.get_match(conn, mid)
    # round 'GF' is stored verbatim but the match is NOT auto-classified
    assert m["round"] == "GF"
    assert m["classification"] == "unclassified" and m["classification_verified"] is False
    assert m["status"] == "draft" and m["include_in_statistics"] is True

    # an administrator sets the classification explicitly
    matches.set_classification(conn, wid, ACTOR, mid, classification="grand_final",
                               finals_stage="grand_final", verified=True)
    m = matches.get_match(conn, mid)
    assert m["classification"] == "grand_final" and m["classification_verified"] is True


def test_list_and_filter(conn):
    wid = _ws(conn, "MATCH WS2")
    cid = _comp(conn, wid)
    g = competitions.create_grade(conn, wid, ACTOR, cid, name="A")
    s = competitions.create_season(conn, wid, ACTOR, cid, label="2025/26")
    m1 = matches.create_match(conn, wid, ACTOR, competition_id=cid, grade_id=g, season_id=s, match_date=date(2025, 11, 1))
    matches.create_match(conn, wid, ACTOR, competition_id=cid, match_date=date(2025, 12, 1))
    assert len(matches.list_matches(conn, season_id=s)) == 1
    assert m1 in {x["id"] for x in matches.list_matches(conn, competition_id=cid)}
    assert len(matches.list_matches(conn, date_from=date(2025, 11, 15))) == 1


# ----------------------------------------------- teams, result, margins


def test_teams_and_result(conn):
    wid = _ws(conn, "MATCH WS3")
    cid = _comp(conn, wid)
    org = _org(conn, wid, "Club")
    home = _team(conn, wid, org, "Home XI")
    away = _team(conn, wid, org, "Away XI")
    cap = _person(conn, wid, "Captain")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=cid)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True, captain_person_id=cap)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    teams = matches.list_match_teams(conn, mid)
    assert {t["is_home"] for t in teams} == {True, False}
    home_row = next(t for t in teams if t["is_home"])
    assert home_row["captain_person_id"] == cap

    matches.set_result(conn, wid, ACTOR, mid, result_type="home_win", won_by_team_id=home, margin_runs=42)
    m = matches.get_match(conn, mid)
    assert m["result_type"] == "home_win" and m["won_by_team_id"] == home and m["margin_runs"] == 42
    # a winner must be a side of the match
    with pytest.raises(ValueError, match="winner_not_in_match"):
        matches.set_result(conn, wid, ACTOR, mid, result_type="away_win", won_by_team_id=uuid.uuid4())


def test_one_home_one_away(conn):
    wid = _ws(conn, "MATCH WS3b")
    cid = _comp(conn, wid)
    org = _org(conn, wid, "Club")
    a = _team(conn, wid, org, "A"); b = _team(conn, wid, org, "B"); c = _team(conn, wid, org, "C")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=cid)
    matches.set_team(conn, wid, ACTOR, mid, team_id=a, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=b, is_home=False)
    # a second home side is rejected by the unique side index
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        matches.set_team(conn, wid, ACTOR, mid, team_id=c, is_home=True)


# ----------------------------------------------- playing-condition resolution at match scope


def test_match_scope_playing_conditions_resolve(conn):
    wid = _ws(conn, "MATCH WS4")
    cid = _comp(conn, wid)
    g = competitions.create_grade(conn, wid, ACTOR, cid, name="A")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=cid, grade_id=g)
    # competition sets balls_per_over 6; grade overrides overs_limit; match overrides overs_limit again
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="competition", target_id=cid, balls_per_over=6)
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="grade", target_id=g, overs_limit=50)
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="match", target_id=mid, overs_limit=20)
    eff = matches.effective_conditions(conn, mid)
    assert eff["conditions"]["overs_limit"] == 20  # match wins
    assert eff["conditions"]["balls_per_over"] == 6  # inherited from competition
    assert eff["sources"]["overs_limit"] == "match"


def test_match_id_fks_resolved(conn):
    """The reserved match_id columns now reference match: a match-scope playing condition and a
    finals-series game can be linked to a real match, and a bad match id is rejected by the FK."""
    wid = _ws(conn, "MATCH WS5")
    cid = _comp(conn, wid)
    mid = matches.create_match(conn, wid, ACTOR, competition_id=cid)
    # playing_condition.match_id -> match (set_conditions already used match scope above)
    playing_conditions.set_conditions(conn, wid, ACTOR, scope="match", target_id=mid, overs_limit=40)
    # finals_series_game.match_id -> match
    sid = finals_series.create_series(conn, wid, ACTOR, competition_id=cid, name="GF Series", format="single")
    finals_series.add_game(conn, wid, ACTOR, sid, game_number=1, match_id=mid)
    assert finals_series.list_games(conn, sid)[0]["match_id"] == mid
    # a non-existent match id violates the new FK
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        finals_series.add_game(conn, wid, ACTOR, sid, game_number=2, match_id=uuid.uuid4())


# ----------------------------------------------- isolation / permissions / audit / validation


def test_isolation(conn):
    wid_a = _mk_workspace(conn, "MATCH ISO A")
    wid_b = _mk_workspace(conn, "MATCH ISO B")
    set_workspace(conn, wid_a)
    cid = competitions.create_competition(conn, wid_a, ACTOR, name="A League")
    mid = matches.create_match(conn, wid_a, ACTOR, competition_id=cid)
    set_workspace(conn, wid_b)
    assert matches.get_match(conn, mid) is None
    assert matches.list_matches(conn) == []


def test_permission_and_audit(conn):
    wid = _ws(conn, "MATCH PERM")
    admin = _mk_user(conn, "match_admin")
    viewer = _mk_user(conn, "match_viewer")
    permissions.grant_role(conn, admin, wid, "workspace_admin")
    permissions.grant_role(conn, viewer, wid, "viewer")
    assert "match.manage" in permissions.effective_permissions(conn, admin, wid, False)
    assert "match.manage" not in permissions.effective_permissions(conn, viewer, wid, False)

    cid = _comp(conn, wid)
    mid = matches.create_match(conn, wid, ACTOR, competition_id=cid, round="1")
    matches.set_classification(conn, wid, ACTOR, mid, classification="final")
    matches.set_result(conn, wid, ACTOR, mid, result_type="draw")
    actions = conn.execute(text("SELECT action FROM audit_log WHERE action LIKE 'match%'")).scalars().all()
    for expected in ("match.create", "match.classify", "match.result"):
        assert expected in actions


def test_invalid_inputs(conn):
    wid = _ws(conn, "MATCH INVALID")
    with pytest.raises(ValueError, match="competition_not_found"):
        matches.create_match(conn, wid, ACTOR, competition_id=uuid.uuid4())
    mid = matches.create_match(conn, wid, ACTOR)
    with pytest.raises(ValueError, match="invalid_classification"):
        matches.set_classification(conn, wid, ACTOR, mid, classification="semi")
    with pytest.raises(ValueError, match="invalid_result_type"):
        matches.set_result(conn, wid, ACTOR, mid, result_type="won")
