"""Super-Admin user management & secure first-login — security + workflow tests.

Temporary single-use expiring passwords + forced first-login change, suspend/reactivate, last-super-admin
guards, escalation guard, rate limiting, invitations, and secure recovery. Requires a live DB; rolled back.
No plaintext passwords are ever stored (only Argon2id hashes).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text

from onestats.core import security
from onestats.core.config import Settings, get_settings
from onestats.domain import auth, bootstrap, permissions, users

settings = get_settings()
pytestmark = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")
TS = Settings(env="test", db_password=None, _env_file=None)


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


def _admin(conn):
    uid = auth.create_user(conn, f"root-{security.generate_token()[:6]}", "AdminPass123", is_super_admin=True)
    return str(uid)


def test_create_user_issues_temp_password_and_first_login_change(conn):
    actor = _admin(conn)
    res = users.create_user(conn, actor, username="player_one", display_name="Player One")
    temp = res["temp_password"]
    assert temp and len(temp) >= 10
    # the temp password is NOT stored in plaintext (only an Argon2id hash)
    stored = conn.execute(text("SELECT password_hash, must_change_password FROM app_user WHERE username='player_one'")).mappings().one()
    assert stored["password_hash"].startswith("$argon2") and temp not in stored["password_hash"]
    assert stored["must_change_password"] is True
    # login works with the temp password and flags must_change
    u = auth.authenticate(conn, "player_one", temp)
    assert u and u["must_change_password"] is True
    # first-login change clears the flag and the temp no longer works
    auth.change_password(conn, u["id"], "BrandNewPass9")
    assert conn.execute(text("SELECT must_change_password FROM app_user WHERE id=:i"), {"i": u["id"]}).scalar_one() is False
    assert auth.authenticate(conn, "player_one", temp) is None
    assert auth.authenticate(conn, "player_one", "BrandNewPass9") is not None


def test_temp_password_expires(conn):
    actor = _admin(conn)
    res = users.create_user(conn, actor, username="expy")
    # force the temp password to be expired
    conn.execute(text("UPDATE app_user SET password_expires_at = :e WHERE username='expy'"),
                 {"e": datetime.now(UTC) - timedelta(hours=1)})
    assert auth.authenticate(conn, "expy", res["temp_password"]) is None   # expired temp cannot be used


def test_password_strength_and_weak_rejected(conn):
    assert security.password_strength_error("short1") is not None
    assert security.password_strength_error("allletters") is not None      # no digit
    assert security.password_strength_error("ValidPass12") is None


def test_suspend_reactivate_and_last_super_admin_guards(conn):
    actor = _admin(conn)
    res = users.create_user(conn, actor, username="member")
    uid = res["user_id"]
    users.set_status(conn, actor, uid, "suspended")
    assert auth.authenticate(conn, "member", res["temp_password"]) is None   # suspended cannot log in
    users.set_status(conn, actor, uid, "active")
    assert auth.authenticate(conn, "member", res["temp_password"]) is not None
    # make the actor the ONLY active super admin (the shared dev DB may have others) — rolled back after
    conn.execute(text("UPDATE app_user SET status='suspended' WHERE is_super_admin AND status='active' AND id != :a"),
                 {"a": actor})
    # cannot suspend or demote the only Super Admin
    with pytest.raises(ValueError, match="cannot_suspend_last_super_admin"):
        users.set_status(conn, actor, actor, "suspended")
    with pytest.raises(ValueError, match="cannot_demote_last_super_admin"):
        users.set_super_admin(conn, actor, actor, False)


def test_escalation_guard_blocks_super_admin_as_workspace_role(conn):
    wid = conn.execute(text("INSERT INTO workspace(name,type) VALUES ('ESC','club') RETURNING id")).scalar_one()
    from onestats.db.workspace import set_workspace
    set_workspace(conn, wid)
    actor = _admin(conn)
    u = users.create_user(conn, actor, username="clubby")["user_id"]
    with pytest.raises(ValueError, match="cannot_grant_super_admin"):
        permissions.grant_role(conn, u, wid, "super_admin")      # a workspace/club admin can never grant it
    permissions.grant_role(conn, u, wid, "viewer")               # ordinary workspace roles are fine


def test_rate_limiting(conn):
    actor = _admin(conn)
    users.create_user(conn, actor, username="brute")
    for _ in range(8):
        auth.record_attempt(conn, "brute", None, "1.2.3.4", False)
    assert auth.is_rate_limited(conn, "brute") is True
    auth.record_attempt(conn, "brute", None, "1.2.3.4", True)     # a success resets the window
    assert auth.is_rate_limited(conn, "brute") is False


def test_invitation_single_use_and_revoke(conn):
    actor = _admin(conn)
    inv = users.create_invitation(conn, actor, username="invitee", display_name="Invitee")
    token = inv["token"]
    # invited account is not active until accepted
    assert conn.execute(text("SELECT status FROM app_user WHERE username='invitee'")).scalar_one() == "invited"
    users.accept_invitation(conn, token, "InviteePass1")
    assert conn.execute(text("SELECT status FROM app_user WHERE username='invitee'")).scalar_one() == "active"
    assert auth.authenticate(conn, "invitee", "InviteePass1") is not None
    # single-use: the token cannot be reused
    with pytest.raises(ValueError, match="invalid_or_expired_invitation"):
        users.accept_invitation(conn, token, "Another1234")
    # a revoked invitation cannot be accepted
    inv2 = users.create_invitation(conn, actor, username="invitee2")
    users.revoke_invitation(conn, actor, inv2["invitation_id"])
    with pytest.raises(ValueError, match="invalid_or_expired_invitation"):
        users.accept_invitation(conn, inv2["token"], "Another1234")


def test_super_admin_recovery(conn):
    actor = _admin(conn)
    # a second super admin so recovery is testable without the single-admin guard getting in the way
    locked = users.create_user(conn, actor, username="locked_admin", is_super_admin=True)["user_id"]
    token = bootstrap.issue_recovery_token(conn, TS)
    # invalid token is rejected
    with pytest.raises(ValueError, match="invalid_recovery_token"):
        bootstrap.recover_super_admin(conn, TS, "wrong-token-value", "locked_admin", "Recovered123")
    bootstrap.recover_super_admin(conn, TS, token, "locked_admin", "Recovered123")
    row = conn.execute(text("SELECT is_super_admin, status, must_change_password FROM app_user WHERE id=:i"),
                       {"i": locked}).mappings().one()
    assert row["is_super_admin"] and row["status"] == "active" and row["must_change_password"] is True
    assert auth.authenticate(conn, "locked_admin", "Recovered123") is not None
    # the recovery token is single-use
    with pytest.raises(ValueError, match="invalid_recovery_token"):
        bootstrap.recover_super_admin(conn, TS, token, "locked_admin", "Again12345")


def test_user_audit_history(conn):
    actor = _admin(conn)
    res = users.create_user(conn, actor, username="audited")
    uid = res["user_id"]
    auth.record_attempt(conn, "audited", uid, "9.9.9.9", True)
    users.set_status(conn, actor, uid, "suspended")
    hist = users.user_audit(conn, uid)
    assert any(x["success"] for x in hist["logins"])
    assert any(e["action"].startswith("user.") for e in hist["admin_events"])
