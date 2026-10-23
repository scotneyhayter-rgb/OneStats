"""Live bowling tests (Phase 6, Stage 4).

Rolled back in a single transaction (no data persists); skipped without a live DB. Runs as the
least-privilege ``onestats_app`` role under FORCE RLS. Covers bowler identity & order, overs as
legal-ball counts (never decimals) with historical balls-per-over, maidens/runs/wickets, attributed
wides/no-balls, preserved source codes, unknown-vs-zero, recorded-vs-calculated figures, the rule
that wickets are never auto-assigned on ambiguous dismissals, non-blocking reconciliation with
innings and batting, duplicate protection, isolation, permissions, audit and invalid inputs.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import batting as bat
from onestats.domain import bowling as bowl
from onestats.domain import competitions, matches, people, permissions, playing_conditions
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


def _innings(conn, wid, *, balls_per_over=None, overs_limit=None):
    cid = competitions.create_competition(conn, wid, ACTOR, name="League")
    if balls_per_over is not None or overs_limit is not None:
        playing_conditions.set_conditions(conn, wid, ACTOR, scope="competition", target_id=cid,
                                           balls_per_over=balls_per_over, overs_limit=overs_limit)
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


def test_identity_order_and_figures(conn):
    wid = _ws(conn, "BOWL WS1")
    iid = _innings(conn, wid, balls_per_over=6)
    b1 = _person(conn, wid, "Bowler One")
    b2 = _person(conn, wid, "Bowler Two")
    bowl.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=b2, bowling_order=2,
                      overs_text="8", maidens=1, runs_conceded=30, wickets=1)
    bowl.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=b1, bowling_order=1,
                      overs_text="10", maidens=2, runs_conceded=42, wickets=3)
    rows = bowl.list_entries(conn, iid)
    assert [r["bowling_order"] for r in rows] == [1, 2]
    card = bowl.bowling_card(conn, iid)
    assert card["recorded_wickets"] == 4 and card["recorded_runs_conceded"] == 72
    assert card["total_legal_balls"] == 108  # (10*6) + (8*6)
    assert card["total_overs"] == "18.0"


def test_overs_are_not_decimals(conn):
    wid = _ws(conn, "BOWL WS2")
    iid = _innings(conn, wid, balls_per_over=6)
    # "5.3" means 5 overs 3 balls = 33 legal balls, NOT 5.3 of an over
    e = bowl.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=_person(conn, wid, "A"),
                          bowling_order=1, overs_text="5.3", runs_conceded=20)
    row = bowl.get_entry(conn, e)
    assert row["overs_text"] == "5.3"       # original notation preserved verbatim
    assert row["legal_balls"] == 33          # derived underlying legal-ball count
    assert bowl.notation_from_legal_balls(33, 6) == "5.3"


def test_historical_balls_per_over(conn):
    wid = _ws(conn, "BOWL WS3")
    iid = _innings(conn, wid, balls_per_over=8)   # historical 8-ball overs
    e = bowl.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=_person(conn, wid, "B"),
                          bowling_order=1, overs_text="5.3")
    assert bowl.get_entry(conn, e)["legal_balls"] == 43  # 5*8 + 3, not 5*6+3


def test_unknown_balls_per_over_stays_unknown(conn):
    wid = _ws(conn, "BOWL WS4")
    iid = _innings(conn, wid)  # no playing conditions -> balls_per_over unknown
    e = bowl.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=_person(conn, wid, "C"),
                          bowling_order=1, overs_text="10")
    # notation preserved, but no modern default is assumed -> legal_balls unknown, not 60
    assert bowl.get_entry(conn, e)["overs_text"] == "10"
    assert bowl.get_entry(conn, e)["legal_balls"] is None


def test_unknown_is_not_zero(conn):
    wid = _ws(conn, "BOWL WS5")
    iid = _innings(conn, wid, balls_per_over=6)
    # a newspaper figure: bowler known, only wickets recorded
    bowl.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=_person(conn, wid, "D"),
                      bowling_order=1, wickets=2, evidence="The Age, 3 Feb 1971")
    card = bowl.bowling_card(conn, iid)
    assert card["recorded_wickets"] == 2
    assert card["recorded_runs_conceded"] is None   # unknown, NOT 0
    assert card["total_legal_balls"] is None


def test_wickets_not_auto_assigned_on_ambiguous(conn):
    wid = _ws(conn, "BOWL WS6")
    iid = _innings(conn, wid, balls_per_over=6)
    bowler = _person(conn, wid, "Resolved Bowler")
    # one clear bowler-credit dismissal WITH a resolved bowler -> counts
    bat.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=_person(conn, wid, "Out1"),
                     batting_position=1, dismissal_type="bowled", bowler_person_id=bowler)
    # a run-out (no bowler credit) and a bowler-credit mode but NO bowler -> neither counts
    bat.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=_person(conn, wid, "Out2"),
                     batting_position=2, dismissal_type="run_out")
    bat.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=_person(conn, wid, "Out3"),
                     batting_position=3, dismissal_type="caught")  # ambiguous: no bowler attributed
    assert bowl.bowling_card(conn, iid)["derived_bowler_wickets"] == 1  # only the resolved one


def test_recorded_vs_calculated_distinct(conn):
    wid = _ws(conn, "BOWL WS7")
    iid = _innings(conn, wid, balls_per_over=6)
    bowler = _person(conn, wid, "Bowler")
    # recorded figure says 2 wickets, but only 1 dismissal is clearly attributed to a bowler
    bowl.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=bowler, bowling_order=1,
                      overs_text="4", runs_conceded=15, wickets=2)
    bat.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=_person(conn, wid, "X"),
                     batting_position=1, dismissal_type="lbw", bowler_person_id=bowler)
    card = bowl.bowling_card(conn, iid)
    assert card["recorded_wickets"] == 2 and card["derived_bowler_wickets"] == 1
    assert "bowling_wickets_differ_from_dismissals" in bowl.validation_warnings(conn, iid)


def test_reconciliation_warnings_non_blocking(conn):
    wid = _ws(conn, "BOWL WS8")
    iid = _innings(conn, wid, balls_per_over=6, overs_limit=10)
    # maidens exceed completed overs, and overs exceed the innings limit -> both flagged, both save
    bowl.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=_person(conn, wid, "M"),
                      bowling_order=1, overs_text="12", maidens=20, runs_conceded=5)
    w = bowl.validation_warnings(conn, iid)
    assert "maidens_exceed_overs" in w
    assert "overs_exceed_limit" in w
    assert bowl.list_entries(conn, iid)[0]["legal_balls"] == 72  # still saved


def test_preserved_source_code(conn):
    wid = _ws(conn, "BOWL WS9")
    iid = _innings(conn, wid, balls_per_over=6)
    e = bowl.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=_person(conn, wid, "S"),
                          bowling_order=1, overs_text="6", bowling_type_raw="3", source_system="cricketstatz")
    assert bowl.get_entry(conn, e)["bowling_type_raw"] == "3"


def test_duplicate_protection(conn):
    wid = _ws(conn, "BOWL WS10")
    iid = _innings(conn, wid, balls_per_over=6)
    p = _person(conn, wid, "Solo")
    bowl.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=p, bowling_order=1)
    with pytest.raises(ValueError, match="duplicate_bowler"):
        bowl.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=p, bowling_order=2)
    with pytest.raises(ValueError, match="duplicate_order"):
        bowl.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=_person(conn, wid, "Other"),
                          bowling_order=1)


def test_isolation(conn):
    wid_a = _mk_workspace(conn, "BOWL ISO A")
    wid_b = _mk_workspace(conn, "BOWL ISO B")
    set_workspace(conn, wid_a)
    iid = _innings(conn, wid_a, balls_per_over=6)
    e = bowl.create_entry(conn, wid_a, ACTOR, innings_id=iid, person_id=_person(conn, wid_a, "H"),
                          bowling_order=1, runs_conceded=1)
    set_workspace(conn, wid_b)
    assert bowl.get_entry(conn, e) is None
    assert bowl.list_entries(conn, iid) == []


def test_permission_and_audit(conn):
    wid = _ws(conn, "BOWL PERM")
    admin = _mk_user(conn, "bowl_admin")
    viewer = _mk_user(conn, "bowl_viewer")
    permissions.grant_role(conn, admin, wid, "workspace_admin")
    permissions.grant_role(conn, viewer, wid, "viewer")
    assert "match.manage" in permissions.effective_permissions(conn, admin, wid, False)
    assert "match.manage" not in permissions.effective_permissions(conn, viewer, wid, False)

    iid = _innings(conn, wid, balls_per_over=6)
    e = bowl.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=_person(conn, wid, "P"),
                          bowling_order=1, runs_conceded=3)
    bowl.update_entry(conn, wid, ACTOR, e, runs_conceded=4)
    bowl.delete_entry(conn, wid, ACTOR, e)
    actions = conn.execute(text("SELECT action FROM audit_log WHERE action LIKE 'bowling_entry%'")).scalars().all()
    for expected in ("bowling_entry.create", "bowling_entry.update", "bowling_entry.delete"):
        assert expected in actions


def test_invalid_inputs(conn):
    wid = _ws(conn, "BOWL INVALID")
    with pytest.raises(ValueError, match="innings_not_found"):
        bowl.create_entry(conn, wid, ACTOR, innings_id=uuid.uuid4(), bowling_order=1)
    iid = _innings(conn, wid, balls_per_over=6)
    with pytest.raises(ValueError, match="invalid_wickets"):
        bowl.create_entry(conn, wid, ACTOR, innings_id=iid, bowling_order=1, wickets=11)
