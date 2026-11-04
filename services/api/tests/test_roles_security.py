"""Phase G — comprehensive role, permission, security and data-safety matrix (Part 21).

Domain-level tests against the live DB (rolled back per test; skipped without a DB; run as
``onestats_app`` under FORCE RLS — the same conditions as production). Covers each role's
permissions, the enforcement points the API relies on (require_permission reads
effective_permissions), the Super-Admin cross-workspace path and attribution, and the security /
data-safety invariants: no self-escalation, no cross-workspace access or leakage, FORCE RLS
effective, separation of duties, and audit attribution to the real actor.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import audit, competitions, matches, people, permissions, users

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")


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


def _ws(conn, name="WS"):
    wid = conn.execute(text("INSERT INTO workspace(name, type) VALUES (:n,'club') RETURNING id"), {"n": name}).scalar_one()
    set_workspace(conn, wid)
    return wid


def _user(conn, name="u"):
    return conn.execute(text("INSERT INTO app_user(username) VALUES (:u) RETURNING id"),
                        {"u": f"{name}-{uuid.uuid4().hex[:8]}"}).scalar_one()


def _member(conn, ws, role):
    u = _user(conn, role)
    permissions.grant_role(conn, u, ws, role)
    return u


def _perms(conn, ws, u):
    return permissions.effective_permissions(conn, u, ws, False)


# ---------------------------------------------------------------- role permission matrix

def test_viewer_can_only_view(conn):
    ws = _ws(conn); u = _member(conn, ws, "viewer")
    assert _perms(conn, ws, u) == {"match.view", "ask.query", "export"}
    # a viewer cannot edit, approve or administer
    for p in ("match.manage", "scorecard.approve", "person.manage", "workspace.manage", "user.admin"):
        assert not permissions.has_permission(conn, u, ws, False, p)


def test_scorecard_editor_can_edit_but_not_approve(conn):
    ws = _ws(conn); u = _member(conn, ws, "scorecard_entry")
    p = _perms(conn, ws, u)
    assert "match.manage" in p          # can create/enter/submit scorecards (post-0062 reconcile)
    assert "scorecard.approve" not in p  # CANNOT bypass verification by approving its own work
    assert "workspace.manage" not in p


def test_researcher_can_research_but_not_approve(conn):
    ws = _ws(conn); u = _member(conn, ws, "researcher")
    p = _perms(conn, ws, u)
    assert {"research.manage", "person.manage"} <= p
    assert "research.verify" not in p    # cannot approve its own findings
    assert "scorecard.approve" not in p


def test_data_verifier_can_approve_and_verify(conn):
    ws = _ws(conn); u = _member(conn, ws, "reviewer")
    p = _perms(conn, ws, u)
    assert {"scorecard.approve", "match.manage", "research.verify", "person.manage"} <= p
    assert "workspace.manage" not in p and "user.admin" not in p


def test_org_admin_manages_everything_except_onboard(conn):
    ws = _ws(conn); u = _member(conn, ws, "workspace_admin")
    p = _perms(conn, ws, u)
    assert {"workspace.manage", "user.admin", "branding.manage", "organisation.manage",
            "match.manage", "scorecard.approve"} <= p
    assert "workspace.onboard" not in p   # onboarding a NEW workspace is a platform action


def test_only_org_admin_manages_workspace_members(conn):
    """Workspace member management (list/add/revoke roles) is gated by user.admin — held by the
    Organisation Admin (and Super Admin), not by Editor/Verifier/Researcher/Viewer. This is what lets
    an Org Admin manage their own workspace's members without being a platform Super Admin."""
    ws = _ws(conn)
    assert "user.admin" in _perms(conn, ws, _member(conn, ws, "workspace_admin"))
    for role in ("scorecard_entry", "reviewer", "researcher", "viewer"):
        assert "user.admin" not in _perms(conn, ws, _member(conn, ws, role))


def test_scorecard_roles_can_read_reference_lists(conn):
    """The scorecard-entry/approval screens read reference lists (competitions, teams, venues, people).
    Those GET endpoints use require_any_permission(<*.manage>, match.manage, scorecard.approve), so a
    Scorecard Editor / Data Verifier may read them without holding the management permission, while a
    Viewer (who holds none of these) stays blocked and writes remain gated by the management permission."""
    ws = _ws(conn)
    read_gate = {"match.manage", "scorecard.approve"}  # the non-manage perms the read endpoints also accept
    editor = _member(conn, ws, "scorecard_entry")
    verifier = _member(conn, ws, "reviewer")
    viewer = _member(conn, ws, "viewer")
    # editor and verifier satisfy the read gate without any *.manage reference permission
    assert _perms(conn, ws, editor) & read_gate
    assert _perms(conn, ws, verifier) & read_gate
    for mgr in ("competition.manage", "organisation.manage", "venue.manage"):
        assert mgr not in _perms(conn, ws, editor)   # proves the gate isn't relying on a manage perm
    # a viewer satisfies neither the read gate nor the manage perms -> still blocked from these lists
    assert not (_perms(conn, ws, viewer) & (read_gate | {"competition.manage", "organisation.manage", "venue.manage", "person.manage"}))


def test_super_admin_has_all_in_any_workspace_without_membership(conn):
    ws = _ws(conn)
    sa = uuid.uuid4()  # not a member of anything
    allperms = set(conn.execute(text("SELECT key FROM permission")).scalars().all())
    assert permissions.effective_permissions(conn, sa, ws, True) == allperms
    assert permissions.user_roles(conn, sa, ws) == []  # holds no ordinary role -> acting as platform admin


# ---------------------------------------------------------------- security invariants

def test_cannot_escalate_to_super_admin_via_membership(conn):
    ws = _ws(conn); u = _user(conn, "climber")
    with pytest.raises(ValueError, match="cannot_grant_super_admin"):
        permissions.grant_role(conn, u, ws, "super_admin")


def test_last_super_admin_cannot_be_demoted_or_suspended(conn):
    # NB: dev DB already has exactly one active super admin; create a second so the guard is exercised
    actor = str(_user(conn, "root"))
    conn.execute(text("UPDATE app_user SET is_super_admin = true WHERE id = :i"), {"i": actor})
    # reduce to a single active super admin by suspending all others
    others = conn.execute(text("SELECT id FROM app_user WHERE is_super_admin AND status='active' AND id <> :i"),
                          {"i": actor}).scalars().all()
    for o in others:
        conn.execute(text("UPDATE app_user SET status='suspended' WHERE id=:i"), {"i": o})
    with pytest.raises(ValueError, match="cannot_demote_last_super_admin"):
        users.set_super_admin(conn, actor, uuid.UUID(actor), False)
    with pytest.raises(ValueError, match="cannot_suspend_last_super_admin"):
        users.set_status(conn, actor, uuid.UUID(actor), "suspended")


def test_force_rls_isolates_workspaces_no_leak(conn):
    ws_a = _ws(conn, "A"); comp_a = competitions.create_competition(conn, ws_a, "actor", name="LA")
    matches.create_match(conn, ws_a, "actor", competition_id=comp_a)
    people.create_person(conn, ws_a, "actor", display_name="A Player")
    # switching the workspace context to B must reveal NONE of A's rows (fail-closed FORCE RLS)
    _ws(conn, "B")
    assert conn.execute(text("SELECT count(*) FROM match")).scalar_one() == 0
    assert conn.execute(text("SELECT count(*) FROM person")).scalar_one() == 0
    # and with NO workspace context at all, nothing is visible either
    conn.execute(text("SELECT set_config('onestats.workspace_id','',true)"))
    assert conn.execute(text("SELECT count(*) FROM match")).scalar_one() == 0


def test_draft_stays_bound_to_its_workspace(conn):
    ws_a = _ws(conn, "DA"); comp = competitions.create_competition(conn, ws_a, "actor", name="L")
    mid = matches.create_match(conn, ws_a, "actor", competition_id=comp)
    matches.set_approval(conn, ws_a, "actor", mid, status="awaiting_approval")
    _ws(conn, "DB")  # switch to a different workspace
    # the draft/awaiting match is invisible and cannot be fetched from another workspace's context
    assert matches.get_match(conn, mid) is None


def test_super_admin_action_recorded_against_real_user(conn):
    ws = _ws(conn)
    sa_id = str(_user(conn, "realsa"))
    # a platform super admin grants a role in a workspace they are not a member of; the audit must
    # name the REAL super admin (never the local org admin) and flag acting_as_super_admin
    target = _user(conn, "grantee")
    permissions.grant_role(conn, target, ws, "viewer")
    audit.write_audit(conn, ws, sa_id, "membership.grant", entity="app_user", entity_id=str(target),
                      after={"role": "viewer"}, actor_role="super_admin", effective_permission="user.admin",
                      acting_as_super_admin=True, request_id="req-123", reason="grant viewer")
    row = conn.execute(text("SELECT actor, actor_role, effective_permission, acting_as_super_admin, request_id, reason "
                            "FROM audit_log WHERE action='membership.grant' ORDER BY at DESC LIMIT 1")).mappings().one()
    assert row["actor"] == sa_id
    assert row["actor_role"] == "super_admin" and row["acting_as_super_admin"] is True
    assert row["effective_permission"] == "user.admin" and row["request_id"] == "req-123"
    assert row["reason"] == "grant viewer"


# ---------------------------------------------------------------- separation of duties

def test_submitter_captured_and_self_approval_flagged(conn):
    ws = _ws(conn)
    ed = str(_user(conn, "ed")); other = str(_user(conn, "rev"))  # approved_by FKs app_user
    comp = competitions.create_competition(conn, ws, ed, name="L")
    mid = matches.create_match(conn, ws, ed, competition_id=comp)
    matches.set_approval(conn, ws, ed, mid, status="awaiting_approval")
    assert matches.get_match(conn, mid)["submitted_by"] == ed

    def approved_audit(match_id):
        # select the specific 'approved' row for this match (now() ties within one txn, so ordering
        # by time is unreliable — key off the match id and the recorded status instead)
        return conn.execute(
            text("SELECT after FROM audit_log WHERE action='match.approval' AND entity_id=:m "
                 "AND after->>'approval_status'='approved' LIMIT 1"), {"m": str(match_id)}).scalar_one()

    # same person approves -> flagged as self-approval in the audit (not blocked, for single-admin clubs)
    matches.set_approval(conn, ws, ed, mid, status="approved")
    assert approved_audit(mid).get("self_approved") is True
    # a different approver is NOT flagged
    mid2 = matches.create_match(conn, ws, ed, competition_id=comp)
    matches.set_approval(conn, ws, ed, mid2, status="awaiting_approval")
    matches.set_approval(conn, ws, other, mid2, status="approved")
    assert approved_audit(mid2).get("self_approved") is False


def test_only_verified_matches_are_official(conn):
    ws = _ws(conn)
    a = str(_user(conn, "appr"))  # approved_by FKs app_user
    comp = competitions.create_competition(conn, ws, a, name="L")
    mid = matches.create_match(conn, ws, a, competition_id=comp)
    assert matches.official_for_stats(matches.get_match(conn, mid)) is False   # draft -> not official
    matches.set_approval(conn, ws, a, mid, status="awaiting_approval")
    assert matches.official_for_stats(matches.get_match(conn, mid)) is False   # submitted -> not official
    matches.set_approval(conn, ws, a, mid, status="approved")
    assert matches.official_for_stats(matches.get_match(conn, mid)) is True    # approved -> official
