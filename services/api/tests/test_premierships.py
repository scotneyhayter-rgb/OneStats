"""Live premiership & finals-series-linkage tests (Phase 6, Stage 6).

Rolled back in a single transaction (no data persists); skipped without a live DB. Runs as the
least-privilege ``onestats_app`` role under FORCE RLS. Covers premiership records (winner, runner-up,
shared, abandoned, not-awarded, verification, evidence), the rule that a premiership is never
auto-awarded from a Grand Final result, series linkage with sequence + relationship (game_label)
and match validation, unknown-vs-zero, non-blocking validation, isolation, permissions, audit and
invalid inputs.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import competitions, finals_series, matches, permissions
from onestats.domain import premierships as prem

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


def test_premiership_with_winner_and_runner_up(conn):
    wid = _ws(conn, "PREM WS1")
    cid = competitions.create_competition(conn, wid, ACTOR, name="A Grade")
    org = _org(conn, wid, "Club")
    winner = _team(conn, wid, org, "Winners")
    runner = _team(conn, wid, org, "Runners")
    p = prem.create_premiership(conn, wid, ACTOR, competition_id=cid, outcome="awarded",
                                runner_up_team_id=runner, verification_status="verified",
                                evidence="RDCA 1975-76 annual report")
    prem.add_winner(conn, wid, ACTOR, p, winner)
    d = prem.detail(conn, p)
    assert d["outcome"] == "awarded" and d["runner_up_team_id"] == runner
    assert d["verification_status"] == "verified"
    assert [w["team_id"] for w in d["winners"]] == [winner]
    assert prem.validation_warnings(conn, p) == []


def test_shared_premiership(conn):
    wid = _ws(conn, "PREM WS2")
    cid = competitions.create_competition(conn, wid, ACTOR, name="B Grade")
    org = _org(conn, wid, "Club")
    a = _team(conn, wid, org, "Team A")
    b = _team(conn, wid, org, "Team B")
    p = prem.create_premiership(conn, wid, ACTOR, competition_id=cid, outcome="shared",
                                verification_status="verified", evidence="finals abandoned, title shared")
    prem.add_winner(conn, wid, ACTOR, p, a, role="shared_winner")
    prem.add_winner(conn, wid, ACTOR, p, b, role="shared_winner")
    assert len(prem.list_winners(conn, p)) == 2
    assert prem.validation_warnings(conn, p) == []  # shared with two winners is consistent


def test_abandoned_and_not_awarded(conn):
    wid = _ws(conn, "PREM WS3")
    cid = competitions.create_competition(conn, wid, ACTOR, name="C Grade")
    ab = prem.create_premiership(conn, wid, ACTOR, competition_id=cid, outcome="abandoned",
                                 evidence="1942 season abandoned (war)")
    na = prem.create_premiership(conn, wid, ACTOR, competition_id=cid, outcome="not_awarded")
    assert prem.get_premiership(conn, ab)["outcome"] == "abandoned"
    assert prem.list_winners(conn, ab) == []     # no winner — unknown preserved, not invented
    assert prem.get_premiership(conn, na)["outcome"] == "not_awarded"


def test_premiership_not_auto_awarded_from_grand_final(conn):
    """Winning a Grand-Final match must NOT, by itself, create a premiership."""
    wid = _ws(conn, "PREM WS4")
    cid = competitions.create_competition(conn, wid, ACTOR, name="A Grade")
    org = _org(conn, wid, "Club")
    home = _team(conn, wid, org, "Home")
    away = _team(conn, wid, org, "Away")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=cid)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    matches.set_classification(conn, wid, ACTOR, mid, classification="grand_final")
    matches.set_result(conn, wid, ACTOR, mid, result_type="home_win", won_by_team_id=home, margin_runs=20)
    # a grand-final win exists, but no premiership was recorded
    assert prem.list_premierships(conn, competition_id=cid) == []


def test_series_linkage_sequence_and_relationship(conn):
    wid = _ws(conn, "PREM WS5")
    cid = competitions.create_competition(conn, wid, ACTOR, name="A Grade")
    org = _org(conn, wid, "Club")
    home = _team(conn, wid, org, "Home")
    away = _team(conn, wid, org, "Away")
    sid = finals_series.create_series(conn, wid, ACTOR, competition_id=cid, name="1975-76 Finals",
                                      format="best_of_3", is_grand_final_series=True)
    mid = matches.create_match(conn, wid, ACTOR, competition_id=cid)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    finals_series.add_game(conn, wid, ACTOR, sid, game_number=1, match_id=mid, game_label="grand_final")
    finals_series.add_game(conn, wid, ACTOR, sid, game_number=2, game_label="replay")
    games = finals_series.list_games(conn, sid)
    assert [g["game_number"] for g in games] == [1, 2]      # sequence
    assert [g["game_label"] for g in games] == ["grand_final", "replay"]  # relationship
    assert games[0]["match_id"] == mid
    # a non-existent match is rejected (FK + clean error)
    with pytest.raises(ValueError, match="match_not_found"):
        finals_series.add_game(conn, wid, ACTOR, sid, game_number=3, match_id=uuid.uuid4())


def test_premiership_can_link_deciding_series_and_match(conn):
    wid = _ws(conn, "PREM WS6")
    cid = competitions.create_competition(conn, wid, ACTOR, name="A Grade")
    org = _org(conn, wid, "Club")
    home = _team(conn, wid, org, "Home")
    sid = finals_series.create_series(conn, wid, ACTOR, competition_id=cid, name="GF Series")
    mid = matches.create_match(conn, wid, ACTOR, competition_id=cid)
    p = prem.create_premiership(conn, wid, ACTOR, competition_id=cid, outcome="awarded",
                                deciding_series_id=sid, deciding_match_id=mid, verification_status="verified")
    prem.add_winner(conn, wid, ACTOR, p, home)
    row = prem.get_premiership(conn, p)
    assert row["deciding_series_id"] == sid and row["deciding_match_id"] == mid


def test_validation_non_blocking(conn):
    wid = _ws(conn, "PREM WS7")
    cid = competitions.create_competition(conn, wid, ACTOR, name="A Grade")
    org = _org(conn, wid, "Club")
    t = _team(conn, wid, org, "T")
    # outcome 'awarded' but no winner, and a winner elsewhere with no evidence/verification
    p1 = prem.create_premiership(conn, wid, ACTOR, competition_id=cid, outcome="awarded")
    assert "awarded_premiership_no_winner" in prem.validation_warnings(conn, p1)
    p2 = prem.create_premiership(conn, wid, ACTOR, competition_id=cid, outcome="shared")
    prem.add_winner(conn, wid, ACTOR, p2, t)
    w = prem.validation_warnings(conn, p2)
    assert "shared_premiership_needs_two_winners" in w  # only one winner
    assert "premiership_unverified_no_evidence" in w    # no evidence/verification/deciding link
    assert prem.get_premiership(conn, p2) is not None    # still saved


def test_isolation(conn):
    wid_a = _mk_workspace(conn, "PREM ISO A")
    wid_b = _mk_workspace(conn, "PREM ISO B")
    set_workspace(conn, wid_a)
    cid = competitions.create_competition(conn, wid_a, ACTOR, name="A Grade")
    org = _org(conn, wid_a, "Club")
    t = _team(conn, wid_a, org, "T")
    p = prem.create_premiership(conn, wid_a, ACTOR, competition_id=cid, outcome="awarded")
    prem.add_winner(conn, wid_a, ACTOR, p, t)
    set_workspace(conn, wid_b)
    assert prem.get_premiership(conn, p) is None
    assert prem.list_winners(conn, p) == []
    assert prem.list_premierships(conn, competition_id=cid) == []


def test_cross_workspace_link_rejected(conn):
    """A premiership cannot reference a competition from another workspace (RLS hides it)."""
    wid_a = _mk_workspace(conn, "PREM XW A")
    set_workspace(conn, wid_a)
    cid_a = competitions.create_competition(conn, wid_a, ACTOR, name="A Grade")
    wid_b = _mk_workspace(conn, "PREM XW B")
    set_workspace(conn, wid_b)
    # competition cid_a belongs to workspace A; under B's GUC it is invisible -> not_found
    with pytest.raises(ValueError, match="competition_not_found"):
        prem.create_premiership(conn, wid_b, ACTOR, competition_id=cid_a, outcome="awarded")


def test_permission_and_audit(conn):
    wid = _ws(conn, "PREM PERM")
    admin = _mk_user(conn, "prem_admin")
    viewer = _mk_user(conn, "prem_viewer")
    permissions.grant_role(conn, admin, wid, "workspace_admin")
    permissions.grant_role(conn, viewer, wid, "viewer")
    assert "competition.manage" in permissions.effective_permissions(conn, admin, wid, False)
    assert "competition.manage" not in permissions.effective_permissions(conn, viewer, wid, False)

    cid = competitions.create_competition(conn, wid, ACTOR, name="A Grade")
    org = _org(conn, wid, "Club")
    t = _team(conn, wid, org, "T")
    p = prem.create_premiership(conn, wid, ACTOR, competition_id=cid, outcome="awarded")
    prem.add_winner(conn, wid, ACTOR, p, t)
    prem.update_premiership(conn, wid, ACTOR, p, verification_status="verified")
    prem.remove_winner(conn, wid, ACTOR, p, t)
    prem.delete_premiership(conn, wid, ACTOR, p)
    actions = conn.execute(text("SELECT action FROM audit_log WHERE action LIKE 'premiership%'")).scalars().all()
    for expected in ("premiership.create", "premiership.add_winner", "premiership.update",
                     "premiership.remove_winner", "premiership.delete"):
        assert expected in actions


def test_invalid_inputs(conn):
    wid = _ws(conn, "PREM INVALID")
    cid = competitions.create_competition(conn, wid, ACTOR, name="A Grade")
    with pytest.raises(ValueError, match="invalid_outcome"):
        prem.create_premiership(conn, wid, ACTOR, competition_id=cid, outcome="champion")
    with pytest.raises(ValueError, match="invalid_verification_status"):
        prem.create_premiership(conn, wid, ACTOR, competition_id=cid, verification_status="maybe")
    with pytest.raises(ValueError, match="competition_not_found"):
        prem.create_premiership(conn, wid, ACTOR, competition_id=uuid.uuid4(), outcome="awarded")
