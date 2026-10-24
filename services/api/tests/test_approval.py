"""Scorecard approval workflow + match validation aggregation (Phase 7, Stage 7.1).

Rolled back per test; skipped without a live DB; runs as ``onestats_app`` under FORCE RLS. Covers
the draft→awaiting→approved/rejected transitions (separate from match status), approved-only
statistical eligibility, the revised-since-approval flag, that existing/imported matches are NOT
auto-approved, the scorecard.approve permission, and the validation aggregation.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import competitions, matches, permissions, results, validation
from onestats.domain import innings as inn

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
    # the system ACTOR must exist as a user because match.approved_by references app_user
    conn.execute(text("INSERT INTO app_user(id, username) VALUES (:a, :u) ON CONFLICT (id) DO NOTHING"),
                 {"a": ACTOR, "u": f"actor-{name}"})
    set_workspace(conn, wid)
    return wid


def _user(conn, u):
    return conn.execute(text("INSERT INTO app_user(username) VALUES (:u) RETURNING id"), {"u": u}).scalar_one()


def _match(conn, wid):
    cid = competitions.create_competition(conn, wid, ACTOR, name="League")
    return matches.create_match(conn, wid, ACTOR, competition_id=cid), cid


def test_new_match_defaults_to_draft_not_approved(conn):
    wid = _ws(conn, "APP DRAFT")
    mid, _ = _match(conn, wid)
    m = matches.get_match(conn, mid)
    assert m["approval_status"] == "draft"                       # never auto-approved
    assert matches.official_for_stats(m) is False


def test_approval_transitions_and_audit(conn):
    wid = _ws(conn, "APP FLOW")
    mid, _ = _match(conn, wid)
    matches.set_approval(conn, wid, ACTOR, mid, status="awaiting_approval")
    assert matches.get_match(conn, mid)["approval_status"] == "awaiting_approval"
    matches.set_approval(conn, wid, ACTOR, mid, status="rejected", reason="totals look wrong")
    m = matches.get_match(conn, mid)
    assert m["approval_status"] == "rejected" and m["approval_reason"] == "totals look wrong"
    # resubmit and approve
    matches.set_approval(conn, wid, ACTOR, mid, status="awaiting_approval")
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    m = matches.get_match(conn, mid)
    assert m["approval_status"] == "approved" and m["approved_at"] is not None
    # the cricket status is independent and untouched
    assert m["status"] == "draft"
    actions = conn.execute(text("SELECT count(*) FROM audit_log WHERE action = 'match.approval'")).scalar_one()
    assert actions >= 4


def test_only_approved_contributes_to_official_stats(conn):
    wid = _ws(conn, "APP OFFICIAL")
    mid, _ = _match(conn, wid)
    for st in ("draft", "awaiting_approval", "rejected"):
        matches.set_approval(conn, wid, ACTOR, mid, status=st)
        assert matches.official_for_stats(matches.get_match(conn, mid)) is False
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    assert matches.official_for_stats(matches.get_match(conn, mid)) is True


def test_revision_flag_set_on_edit_and_cleared_on_reapproval(conn):
    wid = _ws(conn, "APP REVISE")
    mid, _ = _match(conn, wid)
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")
    assert matches.get_match(conn, mid)["revised_since_approval"] is False
    matches.mark_revised_if_approved(conn, mid)                  # scorecard edited after approval
    assert matches.get_match(conn, mid)["revised_since_approval"] is True
    matches.set_approval(conn, wid, ACTOR, mid, status="approved")   # re-approve
    assert matches.get_match(conn, mid)["revised_since_approval"] is False


def test_invalid_status_rejected(conn):
    wid = _ws(conn, "APP INVALID")
    mid, _ = _match(conn, wid)
    with pytest.raises(ValueError, match="invalid_approval_status"):
        matches.set_approval(conn, wid, ACTOR, mid, status="finalised")


def test_scorecard_approve_permission_matrix(conn):
    wid = _ws(conn, "APP PERM")
    admin, viewer = _user(conn, "app_admin"), _user(conn, "app_viewer")
    permissions.grant_role(conn, admin, wid, "workspace_admin")
    permissions.grant_role(conn, viewer, wid, "viewer")
    assert "scorecard.approve" in permissions.effective_permissions(conn, admin, wid, False)
    assert "scorecard.approve" not in permissions.effective_permissions(conn, viewer, wid, False)


def test_match_validation_aggregates_warnings(conn):
    """A recorded result that conflicts with the scorecard appears in the match validation list."""
    wid = _ws(conn, "APP VALIDATE")
    cid = competitions.create_competition(conn, wid, ACTOR, name="League")
    org = conn.execute(text("INSERT INTO organisation(workspace_id,name,kind) VALUES (:w,'C','club') RETURNING id"), {"w": wid}).scalar_one()
    home = conn.execute(text("INSERT INTO team(workspace_id,organisation_id,name) VALUES (:w,:o,'Home') RETURNING id"), {"w": wid, "o": org}).scalar_one()
    away = conn.execute(text("INSERT INTO team(workspace_id,organisation_id,name) VALUES (:w,:o,'Away') RETURNING id"), {"w": wid, "o": org}).scalar_one()
    mid = matches.create_match(conn, wid, ACTOR, competition_id=cid)
    matches.set_team(conn, wid, ACTOR, mid, team_id=home, is_home=True)
    matches.set_team(conn, wid, ACTOR, mid, team_id=away, is_home=False)
    i1 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=1, batting_team_id=home, bowling_team_id=away)
    i2 = inn.create_innings(conn, wid, ACTOR, match_id=mid, inns_number=2, batting_team_id=away, bowling_team_id=home, status="completed")
    inn.set_official_total(conn, wid, ACTOR, i1, total=150, wickets=None, reason="t")
    inn.set_official_total(conn, wid, ACTOR, i2, total=120, wickets=10, reason="t")  # scorecard => home by 30
    matches.set_result(conn, wid, ACTOR, mid, result_type="away_win", won_by_team_id=away, margin_runs=5, result_source="recorded")
    v = validation.match_validation(conn, mid)
    assert any(w["area"] == "result" and "result_conflict" in w["code"] for w in v)
    assert all({"scope", "area", "code"} <= set(w) for w in v)   # each tagged with scope/area/reason
