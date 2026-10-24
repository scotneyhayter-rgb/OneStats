"""Live permission/membership/audit tests (rolled back; skipped without a DB)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import audit, permissions

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


def _mk_workspace(conn, name):
    return conn.execute(
        text("INSERT INTO workspace(name, type) VALUES (:n,'club') RETURNING id"), {"n": name}
    ).scalar_one()


def _mk_user(conn, username):
    return conn.execute(
        text("INSERT INTO app_user(username) VALUES (:u) RETURNING id"), {"u": username}
    ).scalar_one()


def test_role_permissions_follow_the_matrix(conn):
    ws = _mk_workspace(conn, "RBAC WS")
    user = _mk_user(conn, "rbac_user")
    set_workspace(conn, ws)

    permissions.grant_role(conn, user, ws, "viewer")
    perms = permissions.effective_permissions(conn, user, ws, False)
    assert perms == {"match.view", "ask.query", "export"}
    assert permissions.has_permission(conn, user, ws, False, "match.view")
    assert not permissions.has_permission(conn, user, ws, False, "record.verify")

    permissions.grant_role(conn, user, ws, "reviewer")
    perms2 = permissions.effective_permissions(conn, user, ws, False)
    assert "record.verify" in perms2 and "import.approve" in perms2  # union of roles

    permissions.revoke_role(conn, user, ws, "viewer")
    assert "record.verify" in permissions.effective_permissions(conn, user, ws, False)


def test_super_admin_has_all_permissions_without_membership(conn):
    ws = _mk_workspace(conn, "SA WS")
    perms = permissions.effective_permissions(conn, uuid.uuid4(), ws, True)
    # 24 Phase 3 perms + organisation/venue/competition/import.manage (Phase 4) + person.manage
    # (Phase 5) + match.manage (Phase 6 Stage 1) + scorecard.approve (Phase 7 Stage 7.1).
    assert len(perms) == 31
    assert {"organisation.manage", "venue.manage", "competition.manage", "import.manage",
            "person.manage", "match.manage", "scorecard.approve"} <= perms
    assert permissions.has_permission(conn, uuid.uuid4(), ws, True, "record.verify")


def test_non_member_has_no_permissions(conn):
    ws = _mk_workspace(conn, "NM WS")
    user = _mk_user(conn, "outsider")
    set_workspace(conn, ws)
    assert permissions.effective_permissions(conn, user, ws, False) == set()
    assert not permissions.has_permission(conn, user, ws, False, "match.view")


def test_audit_write_is_workspace_isolated(conn):
    ws_a = _mk_workspace(conn, "AUD A")
    ws_b = _mk_workspace(conn, "AUD B")
    set_workspace(conn, ws_a)
    audit.write_audit(conn, ws_a, "tester", "workspace.manage", entity="workspace",
                      entity_id=str(ws_a), after={"name": "AUD A"})
    assert conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one() == 1
    set_workspace(conn, ws_b)
    assert conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one() == 0
