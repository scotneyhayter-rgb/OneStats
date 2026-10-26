"""Super-Admin user management (post-Phase-17 security work).

Administered user accounts: list/create/edit/suspend, temporary single-use expiring passwords with a
required first-login change, time-limited invitations, cross-workspace role assignment, and a login/admin
audit view. Global (platform-level); every mutating call is Super-Admin-gated at the API. Never stores
plaintext passwords; escalation guards prevent granting system-wide Super Admin except by a Super Admin,
and the last active Super Admin cannot be removed or demoted (so the platform is never locked out).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.core import security

TEMP_PASSWORD_TTL_HOURS = 72
INVITE_TTL_HOURS = 72


def _audit_global(conn: Connection, actor: str, action: str, user_id: UUID | None) -> None:
    # platform-level actions are recorded in the global admin_audit table (audit_log is workspace-scoped)
    conn.execute(
        text("INSERT INTO admin_audit(actor, action, target_user_id) VALUES (:a, :act, :uid)"),
        {"a": actor, "act": action, "uid": user_id},
    )


def list_users(conn: Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("SELECT id, username, display_name, status, is_super_admin, must_change_password, "
             "last_login_at, created_at FROM app_user ORDER BY lower(username)")).mappings().all()
    return [{k: (str(v) if isinstance(v, UUID) else v) for k, v in dict(r).items()} for r in rows]


def _username_taken(conn: Connection, username: str) -> bool:
    return conn.execute(text("SELECT 1 FROM app_user WHERE lower(username) = lower(:u)"),
                        {"u": username}).first() is not None


def create_user(conn: Connection, actor: str, *, username: str, display_name: str | None = None,
                is_super_admin: bool = False) -> dict[str, Any]:
    """Create an account with a generated **temporary** password (single-use; must be changed on first
    login; expires). Returns the temp password once — it is never stored or shown again."""
    if _username_taken(conn, username):
        raise ValueError("username_taken")
    temp = security.generate_temp_password()
    expires = datetime.now(UTC) + timedelta(hours=TEMP_PASSWORD_TTL_HOURS)
    uid = conn.execute(
        text("INSERT INTO app_user(username, display_name, password_hash, is_super_admin, status, "
             "must_change_password, password_expires_at) "
             "VALUES (:u, :d, :p, :s, 'active', true, :e) RETURNING id"),
        {"u": username, "d": display_name, "p": security.hash_password(temp), "s": is_super_admin, "e": expires},
    ).scalar_one()
    _audit_global(conn, actor, "user.create", uid)
    return {"user_id": str(uid), "username": username, "temp_password": temp,
            "temp_password_expires_at": expires.isoformat()}


def issue_temp_password(conn: Connection, actor: str, user_id: UUID) -> dict[str, Any]:
    """Reset a user's password to a new temporary single-use one (admin password reset)."""
    if conn.execute(text("SELECT 1 FROM app_user WHERE id = :id"), {"id": user_id}).first() is None:
        raise ValueError("user_not_found")
    temp = security.generate_temp_password()
    expires = datetime.now(UTC) + timedelta(hours=TEMP_PASSWORD_TTL_HOURS)
    conn.execute(
        text("UPDATE app_user SET password_hash = :p, must_change_password = true, password_expires_at = :e "
             "WHERE id = :id"),
        {"p": security.hash_password(temp), "e": expires, "id": user_id},
    )
    # revoke the user's active sessions so the old password cannot keep a session alive
    conn.execute(text("UPDATE session SET revoked_at = now() WHERE app_user_id = :id AND revoked_at IS NULL"),
                 {"id": user_id})
    _audit_global(conn, actor, "user.reset_password", user_id)
    return {"user_id": str(user_id), "temp_password": temp, "temp_password_expires_at": expires.isoformat()}


def _active_super_admins(conn: Connection) -> int:
    return conn.execute(text("SELECT count(*) FROM app_user WHERE is_super_admin AND status = 'active'")).scalar_one()


def set_status(conn: Connection, actor: str, user_id: UUID, status: str) -> None:
    """Suspend or reactivate an account. The last active Super Admin cannot be suspended."""
    if status not in ("active", "suspended"):
        raise ValueError("invalid_status")
    row = conn.execute(text("SELECT is_super_admin, status FROM app_user WHERE id = :id"),
                       {"id": user_id}).mappings().first()
    if row is None:
        raise ValueError("user_not_found")
    if status == "suspended" and row["is_super_admin"] and _active_super_admins(conn) <= 1:
        raise ValueError("cannot_suspend_last_super_admin")
    conn.execute(text("UPDATE app_user SET status = :s WHERE id = :id"), {"s": status, "id": user_id})
    if status == "suspended":
        conn.execute(text("UPDATE session SET revoked_at = now() WHERE app_user_id = :id AND revoked_at IS NULL"),
                     {"id": user_id})
    _audit_global(conn, actor, f"user.{'suspend' if status == 'suspended' else 'reactivate'}", user_id)


def set_super_admin(conn: Connection, actor: str, user_id: UUID, value: bool) -> None:
    """Grant/revoke the system-wide Super Admin role. The last active Super Admin cannot be demoted."""
    row = conn.execute(text("SELECT is_super_admin, status FROM app_user WHERE id = :id"),
                       {"id": user_id}).mappings().first()
    if row is None:
        raise ValueError("user_not_found")
    if not value and row["is_super_admin"] and _active_super_admins(conn) <= 1:
        raise ValueError("cannot_demote_last_super_admin")
    conn.execute(text("UPDATE app_user SET is_super_admin = :v WHERE id = :id"), {"v": value, "id": user_id})
    _audit_global(conn, actor, "user.super_admin_granted" if value else "user.super_admin_revoked", user_id)


def update_display_name(conn: Connection, actor: str, user_id: UUID, display_name: str | None) -> None:
    if conn.execute(text("SELECT 1 FROM app_user WHERE id = :id"), {"id": user_id}).first() is None:
        raise ValueError("user_not_found")
    conn.execute(text("UPDATE app_user SET display_name = :d WHERE id = :id"), {"d": display_name, "id": user_id})
    _audit_global(conn, actor, "user.update", user_id)


def user_audit(conn: Connection, user_id: UUID, *, limit: int = 100) -> dict[str, Any]:
    """A user's login history + the administrative actions recorded against their account."""
    logins = conn.execute(
        text("SELECT success, ip, at FROM login_attempt WHERE app_user_id = :id "
             "OR lower(username) = lower((SELECT username FROM app_user WHERE id = :id)) "
             "ORDER BY at DESC LIMIT :lim"), {"id": user_id, "lim": limit}).mappings().all()
    admin = conn.execute(
        text("SELECT action, actor, at FROM admin_audit WHERE target_user_id = :id "
             "ORDER BY at DESC LIMIT :lim"), {"id": user_id, "lim": limit}).mappings().all()
    return {"logins": [{"success": r["success"], "ip": r["ip"], "at": r["at"].isoformat() if r["at"] else None}
                       for r in logins],
            "admin_events": [{"action": r["action"], "actor": r["actor"],
                              "at": r["at"].isoformat() if r["at"] else None} for r in admin]}


# --- time-limited, single-use invitations -------------------------------------------------------

def create_invitation(conn: Connection, actor: str, *, username: str, display_name: str | None = None,
                      is_super_admin: bool = False) -> dict[str, Any]:
    """Create an invited account (no password yet) + a single-use, time-limited token. The invitee sets
    their own password via the token to activate — an alternative to issuing a temporary password."""
    if _username_taken(conn, username):
        raise ValueError("username_taken")
    uid = conn.execute(
        text("INSERT INTO app_user(username, display_name, is_super_admin, status) "
             "VALUES (:u, :d, :s, 'invited') RETURNING id"),
        {"u": username, "d": display_name, "s": is_super_admin}).scalar_one()
    token = security.generate_token()
    expires = datetime.now(UTC) + timedelta(hours=INVITE_TTL_HOURS)
    inv_id = conn.execute(
        text("INSERT INTO user_invitation(app_user_id, token_hash, created_by, expires_at) "
             "VALUES (:u, :h, :c, :e) RETURNING id"),
        {"u": uid, "h": security.hash_token(token), "c": actor, "e": expires}).scalar_one()
    _audit_global(conn, actor, "user.invite", uid)
    return {"invitation_id": str(inv_id), "user_id": str(uid), "username": username,
            "token": token, "expires_at": expires.isoformat()}


def list_invitations(conn: Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("SELECT i.id, i.app_user_id, u.username, i.expires_at, i.used_at, i.revoked_at, i.created_at "
             "FROM user_invitation i JOIN app_user u ON u.id = i.app_user_id ORDER BY i.created_at DESC")
    ).mappings().all()
    out = []
    for r in rows:
        now = datetime.now(UTC)
        status = ("revoked" if r["revoked_at"] else "used" if r["used_at"]
                  else "expired" if r["expires_at"] < now else "pending")
        out.append({"id": str(r["id"]), "user_id": str(r["app_user_id"]), "username": r["username"],
                    "status": status, "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None})
    return out


def revoke_invitation(conn: Connection, actor: str, invitation_id: UUID) -> None:
    row = conn.execute(text("SELECT app_user_id, used_at FROM user_invitation WHERE id = :id"),
                       {"id": invitation_id}).mappings().first()
    if row is None:
        raise ValueError("invitation_not_found")
    conn.execute(text("UPDATE user_invitation SET revoked_at = now() WHERE id = :id AND revoked_at IS NULL"),
                 {"id": invitation_id})
    _audit_global(conn, actor, "user.invite_revoked", row["app_user_id"])


def accept_invitation(conn: Connection, token: str, new_password: str) -> dict[str, Any]:
    """Activate an invited account by setting a password via a valid, unexpired, single-use token."""
    err = security.password_strength_error(new_password)
    if err:
        raise ValueError(err)
    row = conn.execute(
        text("SELECT i.id, i.app_user_id, u.username FROM user_invitation i JOIN app_user u ON u.id = i.app_user_id "
             "WHERE i.token_hash = :h AND i.used_at IS NULL AND i.revoked_at IS NULL AND i.expires_at > now()"),
        {"h": security.hash_token(token)}).mappings().first()
    if row is None:
        raise ValueError("invalid_or_expired_invitation")
    conn.execute(
        text("UPDATE app_user SET password_hash = :p, status = 'active', must_change_password = false, "
             "password_expires_at = NULL WHERE id = :id"),
        {"p": security.hash_password(new_password), "id": row["app_user_id"]})
    conn.execute(text("UPDATE user_invitation SET used_at = now() WHERE id = :id"), {"id": row["id"]})
    return {"user_id": str(row["app_user_id"]), "username": row["username"]}
