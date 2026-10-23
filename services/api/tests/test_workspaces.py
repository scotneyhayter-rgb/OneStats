"""Live workspace + onboarding tests (rolled back; skipped without a DB)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_user, set_workspace
from onestats.domain import onboarding, permissions, workspaces

settings = get_settings()
pytestmark = pytest.mark.skipif(
    not settings.db_configured, reason="no live database credential configured"
)


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


def _mk_user(conn, username):
    return conn.execute(
        text("INSERT INTO app_user(username) VALUES (:u) RETURNING id"), {"u": username}
    ).scalar_one()


def test_create_and_duplicate_prevention(conn):
    actor = _mk_user(conn, "creator")
    wid = workspaces.create_workspace(conn, "Rhymney/Moyston CC", "rmcc", "club", actor)
    assert workspaces.get_workspace(conn, wid)["short_name"] == "rmcc"
    with pytest.raises(ValueError, match="duplicate_identifier"):
        workspaces.create_workspace(conn, "Another", "RMCC", "club", actor)  # case-insensitive
    set_workspace(conn, wid)
    created = conn.execute(
        text("SELECT count(*) FROM audit_log WHERE action = 'workspace.create'")
    ).scalar_one()
    assert created >= 1  # audited


def test_invalid_input(conn):
    actor = _mk_user(conn, "creator2")
    with pytest.raises(ValueError, match="missing_required_fields"):
        workspaces.create_workspace(conn, "", "x", "club", actor)
    with pytest.raises(ValueError, match="invalid_type"):
        workspaces.create_workspace(conn, "Ok", "y", "banana", actor)


def test_onboarding_save_resume_activate(conn):
    sa = _mk_user(conn, "superx")
    admin = _mk_user(conn, "wsadmin")
    did = onboarding.start_draft(conn, sa, "club")
    onboarding.save_draft(
        conn, did,
        {"organisation": {"name": "Ararat CC", "short_name": "ararat", "type": "club"}}, 2,
    )
    onboarding.save_draft(
        conn, did,
        {"branding": {"primary": "#123456", "accent": "#abcdef"}, "admin_user_id": str(admin)}, 3,
    )
    resumed = onboarding.get_draft(conn, did)
    assert resumed["current_step"] == 3
    assert resumed["state"]["organisation"]["short_name"] == "ararat"

    wid = onboarding.activate_draft(conn, did, sa)
    assert workspaces.get_workspace(conn, wid)["short_name"] == "ararat"
    set_workspace(conn, wid)
    assert conn.execute(
        text("SELECT primary_colour FROM branding WHERE workspace_id = :w"), {"w": wid}
    ).scalar_one() == "#123456"
    perms = permissions.effective_permissions(conn, admin, wid, False)
    assert {"workspace.manage", "branding.manage"} <= perms  # initial admin assigned
    assert onboarding.get_draft(conn, did)["status"] == "activated"


def test_activation_requires_fields(conn):
    sa = _mk_user(conn, "super2")
    did = onboarding.start_draft(conn, sa)
    with pytest.raises(ValueError, match="missing_required_fields"):
        onboarding.activate_draft(conn, did, sa)


def test_multiple_memberships_and_my_workspaces(conn):
    user = _mk_user(conn, "multi")
    actor = _mk_user(conn, "creator3")
    w1 = workspaces.create_workspace(conn, "WS One", "wsone", "club", actor)
    w2 = workspaces.create_workspace(conn, "WS Two", "wstwo", "club", actor)
    set_workspace(conn, w1)
    permissions.grant_role(conn, user, w1, "viewer")
    set_workspace(conn, w2)
    permissions.grant_role(conn, user, w2, "reviewer")

    set_user(conn, user)
    mine = workspaces.list_for_user(conn, user, False)
    by_name = {m["short_name"]: set(m["roles"]) for m in mine}
    assert {"wsone", "wstwo"} <= set(by_name)
    assert by_name["wsone"] == {"viewer"} and by_name["wstwo"] == {"reviewer"}


def test_non_member_isolated_from_other_workspaces(conn):
    outsider = _mk_user(conn, "nobody")
    actor = _mk_user(conn, "creator4")
    w = workspaces.create_workspace(conn, "Private WS", "privws", "club", actor)
    set_user(conn, outsider)
    assert all(m["short_name"] != "privws" for m in workspaces.list_for_user(conn, outsider, False))
    set_workspace(conn, w)
    assert not workspaces.user_is_member(conn, outsider, w)
