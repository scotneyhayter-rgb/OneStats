"""Live Finals Series tests (Phase 4, Stage 6 — revised).

Rolled back in a single transaction (no data persists); skipped without a live DB. Runs as the
least-privilege ``onestats_app`` role under FORCE RLS. Covers series formats, ordered games,
participating teams, outcome states, the Grand-Final-series vs individual-match distinction, the
appearance-counting structure (3 games -> 3 games / 1 series), linking imported matches by source
ref, isolation, permissions and audit.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import competitions, finals_series, permissions

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


def _club(conn, wid, name):
    return conn.execute(
        text("INSERT INTO organisation(workspace_id, name, kind) "
             "VALUES (:w, :n, 'club') RETURNING id"), {"w": wid, "n": name}
    ).scalar_one()


def _team(conn, wid, org, name):
    return conn.execute(
        text("INSERT INTO team(workspace_id, organisation_id, name) VALUES (:w, :o, :n) RETURNING id"),
        {"w": wid, "o": org, "n": name},
    ).scalar_one()


def _comp(conn, wid, name="League"):
    return competitions.create_competition(conn, wid, ACTOR, name=name)


def test_best_of_three_grand_final_series(conn):
    wid = _ws(conn, "FS WS1")
    comp = _comp(conn, wid)
    org = _club(conn, wid, "Club")
    t1 = _team(conn, wid, org, "RMCC")
    t2 = _team(conn, wid, org, "Swifts")
    sid = finals_series.create_series(
        conn, wid, ACTOR, competition_id=comp, name="2026 B Grade Grand Final Series",
        format="best_of_3", is_grand_final_series=True,
    )
    finals_series.add_team(conn, wid, ACTOR, sid, t1)
    finals_series.add_team(conn, wid, ACTOR, sid, t2)
    # Three ordered games — a 3-game series, not three unrelated matches.
    for g in (1, 2, 3):
        finals_series.add_game(conn, wid, ACTOR, sid, game_number=g, match_source_ref=f"CSGF{g}")
    detail = finals_series.detail(conn, sid)
    assert detail["format"] == "best_of_3" and detail["is_grand_final_series"] is True
    assert [g["game_number"] for g in detail["games"]] == [1, 2, 3]
    assert len(detail["teams"]) == 2

    # Appearance-counting structure: 3 games, but ONE series.
    assert len(detail["games"]) == 3
    assert conn.execute(
        text("SELECT count(*) FROM finals_series WHERE id = :s"), {"s": sid}
    ).scalar_one() == 1

    # Decide the series -> one premiership (winner), counted once regardless of games.
    finals_series.set_outcome(conn, wid, ACTOR, sid, outcome="decided", winner_team_id=t1)
    assert finals_series.get_series(conn, sid)["winner_team_id"] == t1


def test_grand_final_series_distinct_from_grand_final_match(conn):
    """GF1/GF2 imported matches are linked as games of ONE series, not inferred as separate
    series; the series is distinguishable from the individual GF matches it contains."""
    wid = _ws(conn, "FS WS2")
    comp = _comp(conn, wid)
    org = _club(conn, wid, "C")
    t = _team(conn, wid, org, "T")
    sid = finals_series.create_series(conn, wid, ACTOR, competition_id=comp, name="GF Series",
                                      format="best_of_3", is_grand_final_series=True)
    finals_series.add_team(conn, wid, ACTOR, sid, t)
    g1 = finals_series.add_game(conn, wid, ACTOR, sid, game_number=1, match_source_ref="GF1")
    g2 = finals_series.add_game(conn, wid, ACTOR, sid, game_number=2, match_source_ref="GF2")
    assert g1["game_id"] != g2["game_id"]
    # Still exactly one series containing both games.
    games = finals_series.list_games(conn, sid)
    assert {g["match_source_ref"] for g in games} == {"GF1", "GF2"}
    assert conn.execute(text("SELECT count(*) FROM finals_series"), ).scalar_one() == 1


def test_formats_and_outcome_states(conn):
    wid = _ws(conn, "FS WS3")
    comp = _comp(conn, wid)
    for fmt in ("single", "best_of_3", "best_of_5", "custom"):
        sid = finals_series.create_series(conn, wid, ACTOR, competition_id=comp, name=f"S {fmt}", format=fmt)
        assert finals_series.get_series(conn, sid)["format"] == fmt
    sid = finals_series.create_series(conn, wid, ACTOR, competition_id=comp, name="Drawn series", format="single")
    for oc in ("in_progress", "drawn", "tied", "incomplete", "abandoned", "unresolved"):
        finals_series.set_outcome(conn, wid, ACTOR, sid, outcome=oc)
        assert finals_series.get_series(conn, sid)["outcome"] == oc


def test_game_is_idempotent_and_single_match_is_one_game(conn):
    wid = _ws(conn, "FS WS4")
    comp = _comp(conn, wid)
    sid = finals_series.create_series(conn, wid, ACTOR, competition_id=comp, name="Single", format="single")
    finals_series.add_game(conn, wid, ACTOR, sid, game_number=1, match_source_ref="M1")
    again = finals_series.add_game(conn, wid, ACTOR, sid, game_number=1, match_source_ref="M1")
    assert again["created"] is False
    assert len(finals_series.list_games(conn, sid)) == 1  # a single match = one game, not split


def test_invalid_inputs(conn):
    wid = _ws(conn, "FS WS5")
    comp = _comp(conn, wid)
    with pytest.raises(ValueError, match="invalid_format"):
        finals_series.create_series(conn, wid, ACTOR, competition_id=comp, name="X", format="best_of_7")
    with pytest.raises(ValueError, match="competition_not_found"):
        finals_series.create_series(conn, wid, ACTOR, competition_id=uuid.uuid4(), name="X")
    sid = finals_series.create_series(conn, wid, ACTOR, competition_id=comp, name="S", format="single")
    with pytest.raises(ValueError, match="invalid_outcome"):
        finals_series.set_outcome(conn, wid, ACTOR, sid, outcome="banana")
    # a non-participant cannot be the winner
    org = _club(conn, wid, "C")
    outsider = _team(conn, wid, org, "Outsider")
    with pytest.raises(ValueError, match="winner_not_participant"):
        finals_series.set_outcome(conn, wid, ACTOR, sid, outcome="decided", winner_team_id=outsider)


def test_series_isolated_across_workspaces(conn):
    wid_a = _mk_workspace(conn, "FS ISO A")
    wid_b = _mk_workspace(conn, "FS ISO B")
    set_workspace(conn, wid_a)
    comp = _comp(conn, wid_a, "A League")
    sid = finals_series.create_series(conn, wid_a, ACTOR, competition_id=comp, name="A series", format="single")
    set_workspace(conn, wid_b)
    assert finals_series.get_series(conn, sid) is None
    assert finals_series.list_series(conn) == []


def test_permission_and_audit(conn):
    wid = _ws(conn, "FS PERM WS")
    admin = _mk_user(conn, "fs_admin")
    viewer = _mk_user(conn, "fs_viewer")
    permissions.grant_role(conn, admin, wid, "workspace_admin")
    permissions.grant_role(conn, viewer, wid, "viewer")
    assert "competition.manage" in permissions.effective_permissions(conn, admin, wid, False)
    assert "competition.manage" not in permissions.effective_permissions(conn, viewer, wid, False)

    comp = _comp(conn, wid)
    sid = finals_series.create_series(conn, wid, ACTOR, competition_id=comp, name="Audit series", format="single")
    finals_series.set_outcome(conn, wid, ACTOR, sid, outcome="in_progress")
    actions = conn.execute(
        text("SELECT action FROM audit_log WHERE action LIKE 'finals_series%'")
    ).scalars().all()
    assert "finals_series.create" in actions
    assert "finals_series.set_outcome" in actions
