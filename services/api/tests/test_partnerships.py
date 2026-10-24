"""Live fall-of-wicket & partnership tests (Phase 6, Stage 5).

Rolled back in a single transaction (no data persists); skipped without a live DB. Runs as the
least-privilege ``onestats_app`` role under FORCE RLS. Covers fall of wicket (number, score,
players, link to batting records, partial/unknown, duplicate protection), batting partnerships
(runs, participants, wicket-specific, unbroken, retired batters, incomplete), the bowling-
partnership building block (not a batting partnership), unknown-vs-zero, non-blocking validation,
isolation, permissions, audit and invalid inputs.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import batting as bat
from onestats.domain import bowling as bowl
from onestats.domain import competitions, matches, people, permissions
from onestats.domain import innings as inn
from onestats.domain import partnerships as pshp

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


def test_fow_records_and_link_to_batting(conn):
    wid = _ws(conn, "FOW WS1")
    iid = _innings(conn, wid)
    out = _person(conn, wid, "Dismissed")
    partner = _person(conn, wid, "NotOut")
    be = bat.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=out, batting_position=1,
                          runs=23, dismissal_type="bowled")
    f = pshp.create_fow(conn, wid, ACTOR, innings_id=iid, wicket_number=1, team_score=40,
                        dismissed_person_id=out, not_out_person_id=partner, batting_entry_id=be)
    row = pshp.get_fow(conn, f)
    assert row["wicket_number"] == 1 and row["team_score"] == 40
    assert row["dismissed_person_id"] == out and row["batting_entry_id"] == be
    assert [r["wicket_number"] for r in pshp.list_fow(conn, iid)] == [1]


def test_fow_partial_and_duplicate_protection(conn):
    wid = _ws(conn, "FOW WS2")
    iid = _innings(conn, wid)
    # partial FOW: only a score known, no wicket number / players (incomplete historical card)
    f = pshp.create_fow(conn, wid, ACTOR, innings_id=iid, team_score=55, evidence="scorebook fragment")
    assert pshp.get_fow(conn, f)["wicket_number"] is None
    pshp.create_fow(conn, wid, ACTOR, innings_id=iid, wicket_number=2, team_score=70)
    with pytest.raises(ValueError, match="duplicate_wicket_number"):
        pshp.create_fow(conn, wid, ACTOR, innings_id=iid, wicket_number=2, team_score=99)


def test_partnership_participants_and_unbroken(conn):
    wid = _ws(conn, "PART WS1")
    iid = _innings(conn, wid)
    a = _person(conn, wid, "A")
    b = _person(conn, wid, "B")
    p = pshp.create_partnership(conn, wid, ACTOR, innings_id=iid, wicket_number=3, runs=58,
                                balls=90, player1_person_id=a, player2_person_id=b,
                                unbroken=True, end_reason="innings_closed")
    row = pshp.get_partnership(conn, p)
    assert row["runs"] == 58 and row["wicket_number"] == 3
    assert row["unbroken"] is True and row["end_reason"] == "innings_closed"
    assert {row["player1_person_id"], row["player2_person_id"]} == {a, b}


def test_partnership_retired_batter_two_stands_same_wicket(conn):
    wid = _ws(conn, "PART WS2")
    iid = _innings(conn, wid)
    a, b, c = (_person(conn, wid, n) for n in ("A", "B", "C"))
    # a retirement ends a stand without a wicket; the 2nd-wicket partnership then resumes with a
    # new batter -> two partnerships legitimately share wicket_number 2.
    pshp.create_partnership(conn, wid, ACTOR, innings_id=iid, wicket_number=2, runs=30,
                            player1_person_id=a, player2_person_id=b, end_reason="retired")
    pshp.create_partnership(conn, wid, ACTOR, innings_id=iid, wicket_number=2, runs=25,
                            player1_person_id=a, player2_person_id=c, end_reason="wicket")
    assert len(pshp.list_partnerships(conn, iid)) == 2  # both saved — no false rejection
    assert "multiple_partnerships_same_wicket" in pshp.validation_warnings(conn, iid)


def test_unknown_is_not_zero(conn):
    wid = _ws(conn, "PART WS3")
    iid = _innings(conn, wid)
    # partnership with known participants but unknown runs
    pshp.create_partnership(conn, wid, ACTOR, innings_id=iid, wicket_number=1,
                            player1_person_id=_person(conn, wid, "A"),
                            player2_person_id=_person(conn, wid, "B"))
    row = pshp.list_partnerships(conn, iid)[0]
    assert row["runs"] is None  # unknown, NOT 0
    # FOW with unknown score
    f = pshp.create_fow(conn, wid, ACTOR, innings_id=iid, wicket_number=1)
    assert pshp.get_fow(conn, f)["team_score"] is None


def test_validation_non_blocking(conn):
    wid = _ws(conn, "PART WS4")
    iid = _innings(conn, wid)
    # scores that go DOWN as wickets fall — flagged, not rejected
    pshp.create_fow(conn, wid, ACTOR, innings_id=iid, wicket_number=1, team_score=80)
    pshp.create_fow(conn, wid, ACTOR, innings_id=iid, wicket_number=2, team_score=60)
    pshp.create_fow(conn, wid, ACTOR, innings_id=iid, wicket_number=11, team_score=90)
    w = pshp.validation_warnings(conn, iid)
    assert "fow_scores_not_increasing" in w
    assert "fow_wicket_number_gt_10" in w
    assert len(pshp.list_fow(conn, iid)) == 3  # all saved


def test_bowling_partnership_inputs_building_block(conn):
    wid = _ws(conn, "PART WS5")
    iid = _innings(conn, wid)
    b1 = _person(conn, wid, "Bowler1")
    b2 = _person(conn, wid, "Bowler2")
    bowl.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=b1, bowling_order=1)
    bowl.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=b2, bowling_order=2)
    # one wicket clearly credited to b1
    bat.create_entry(conn, wid, ACTOR, innings_id=iid, person_id=_person(conn, wid, "Out"),
                     batting_position=1, dismissal_type="caught", bowler_person_id=b1)
    inputs = pshp.bowling_partnership_inputs(conn, iid)
    by_person = {r["person_id"]: r for r in inputs}
    assert by_person[b1]["credited_wickets"] == 1
    assert by_person[b2]["credited_wickets"] == 0
    # the building block carries the team, so the stats phase can require "same team"
    assert all(r["bowling_team_id"] is not None for r in inputs)


def test_isolation(conn):
    wid_a = _mk_workspace(conn, "P ISO A")
    wid_b = _mk_workspace(conn, "P ISO B")
    set_workspace(conn, wid_a)
    iid = _innings(conn, wid_a)
    f = pshp.create_fow(conn, wid_a, ACTOR, innings_id=iid, wicket_number=1, team_score=10)
    p = pshp.create_partnership(conn, wid_a, ACTOR, innings_id=iid, wicket_number=1, runs=10)
    set_workspace(conn, wid_b)
    assert pshp.get_fow(conn, f) is None
    assert pshp.get_partnership(conn, p) is None
    assert pshp.list_fow(conn, iid) == [] and pshp.list_partnerships(conn, iid) == []


def test_permission_and_audit(conn):
    wid = _ws(conn, "P PERM")
    admin = _mk_user(conn, "p_admin")
    viewer = _mk_user(conn, "p_viewer")
    permissions.grant_role(conn, admin, wid, "workspace_admin")
    permissions.grant_role(conn, viewer, wid, "viewer")
    assert "match.manage" in permissions.effective_permissions(conn, admin, wid, False)
    assert "match.manage" not in permissions.effective_permissions(conn, viewer, wid, False)

    iid = _innings(conn, wid)
    f = pshp.create_fow(conn, wid, ACTOR, innings_id=iid, wicket_number=1, team_score=10)
    pshp.update_fow(conn, wid, ACTOR, f, team_score=12)
    pshp.delete_fow(conn, wid, ACTOR, f)
    p = pshp.create_partnership(conn, wid, ACTOR, innings_id=iid, wicket_number=1, runs=10)
    pshp.update_partnership(conn, wid, ACTOR, p, runs=12)
    pshp.delete_partnership(conn, wid, ACTOR, p)
    actions = conn.execute(
        text("SELECT action FROM audit_log WHERE action LIKE 'fall_of_wicket%' OR action LIKE 'partnership%'")
    ).scalars().all()
    for expected in ("fall_of_wicket.create", "fall_of_wicket.update", "fall_of_wicket.delete",
                     "partnership.create", "partnership.update", "partnership.delete"):
        assert expected in actions


def test_invalid_inputs(conn):
    wid = _ws(conn, "P INVALID")
    with pytest.raises(ValueError, match="innings_not_found"):
        pshp.create_fow(conn, wid, ACTOR, innings_id=uuid.uuid4(), wicket_number=1)
    iid = _innings(conn, wid)
    with pytest.raises(ValueError, match="invalid_end_reason"):
        pshp.create_partnership(conn, wid, ACTOR, innings_id=iid, wicket_number=1, end_reason="vibes")
    same = _person(conn, wid, "Same")
    with pytest.raises(ValueError, match="players_must_differ"):
        pshp.create_partnership(conn, wid, ACTOR, innings_id=iid, wicket_number=1,
                                player1_person_id=same, player2_person_id=same)


def test_derive_partnerships_from_fow_standard(conn):
    wid = _ws(conn, "PART DERIVE")
    iid = _innings(conn, wid)
    outs = [_person(conn, wid, n) for n in ("A", "B", "C", "D")]
    # FOW at 35 / 78 / 112 / 150  ->  partnerships 35, 43, 34, 38 (differences, incl. extras)
    for n, (score, who) in enumerate(zip((35, 78, 112, 150), outs), start=1):
        pshp.create_fow(conn, wid, ACTOR, innings_id=iid, wicket_number=n, team_score=score, dismissed_person_id=who)
    result = pshp.derive_from_fow(conn, wid, ACTOR, iid)
    calc = [p for p in result if p["origin"] == "calculated"]
    assert [p["runs"] for p in calc] == [35, 43, 34, 38]
    assert [p["wicket_number"] for p in calc] == [1, 2, 3, 4]
    assert calc[0]["player1_person_id"] == outs[0]  # dismissed batter is a participant (not invented)
    assert calc[0]["player2_person_id"] is None       # partner not guessed
    # recompute does not duplicate
    again = [p for p in pshp.derive_from_fow(conn, wid, ACTOR, iid) if p["origin"] == "calculated"]
    assert len(again) == 4


def test_derive_preserves_manual_and_flags_conflict(conn):
    wid = _ws(conn, "PART DERIVE2")
    iid = _innings(conn, wid)
    a, b = _person(conn, wid, "A"), _person(conn, wid, "B")
    pshp.create_fow(conn, wid, ACTOR, innings_id=iid, wicket_number=1, team_score=35, dismissed_person_id=a)
    # a MANUAL partnership for wicket 1 with a conflicting figure
    manual = pshp.create_partnership(conn, wid, ACTOR, innings_id=iid, wicket_number=1, runs=99,
                                     player1_person_id=a, player2_person_id=b, origin="manual")
    pshp.derive_from_fow(conn, wid, ACTOR, iid)
    # the manual row still exists (not overwritten) alongside the calculated one
    assert pshp.get_partnership(conn, manual) is not None
    assert pshp.get_partnership(conn, manual)["origin"] == "manual"
    assert any(p["origin"] == "calculated" and p["runs"] == 35 for p in pshp.list_partnerships(conn, iid))
    # conflict between manual (99) and FOW-derived (35) is flagged for review
    assert "partnership_conflicts_fow" in pshp.validation_warnings(conn, iid)


def test_derive_unbroken_final_stand(conn):
    wid = _ws(conn, "PART DERIVE3")
    iid = _innings(conn, wid)
    a = _person(conn, wid, "A")
    pshp.create_fow(conn, wid, ACTOR, innings_id=iid, wicket_number=1, team_score=40, dismissed_person_id=a)
    inn.set_official_total(conn, wid, ACTOR, iid, total=95, wickets=1, reason="scorebook")
    result = [p for p in pshp.derive_from_fow(conn, wid, ACTOR, iid) if p["origin"] == "calculated"]
    assert result[-1]["unbroken"] is True and result[-1]["runs"] == 55  # 95 - 40
