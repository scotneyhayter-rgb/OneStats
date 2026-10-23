"""Authentication service: users, sessions, and super-admin bootstrap (D25/D26).

All functions take a SQLAlchemy Connection so callers control the transaction (and tests
can roll back). No passwords or tokens are logged. Session and user records are global
(not workspace-scoped).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.core import security


# --- settings (key/value) ---
def get_setting(conn: Connection, key: str) -> str | None:
    return conn.execute(
        text("SELECT value FROM system_setting WHERE key = :k"), {"k": key}
    ).scalar_one_or_none()


def set_setting(conn: Connection, key: str, value: str | None) -> None:
    conn.execute(
        text(
            "INSERT INTO system_setting(key, value, updated_at) VALUES (:k, :v, now()) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()"
        ),
        {"k": key, "v": value},
    )


# --- users ---
def count_super_admins(conn: Connection) -> int:
    return conn.execute(
        text("SELECT count(*) FROM app_user WHERE is_super_admin AND status = 'active'")
    ).scalar_one()


def setup_required(conn: Connection) -> bool:
    return count_super_admins(conn) == 0


def get_user_by_username(conn: Connection, username: str) -> dict[str, Any] | None:
    row = conn.execute(
        text(
            "SELECT id, username, display_name, status, is_super_admin, password_hash "
            "FROM app_user WHERE lower(username) = lower(:u)"
        ),
        {"u": username},
    ).mappings().first()
    return dict(row) if row else None


def create_user(
    conn: Connection,
    username: str,
    password: str,
    display_name: str | None = None,
    is_super_admin: bool = False,
) -> UUID:
    pw_hash = security.hash_password(password)
    return conn.execute(
        text(
            "INSERT INTO app_user(username, display_name, password_hash, is_super_admin) "
            "VALUES (:u, :d, :p, :s) RETURNING id"
        ),
        {"u": username, "d": display_name, "p": pw_hash, "s": is_super_admin},
    ).scalar_one()


def authenticate(conn: Connection, username: str, password: str) -> dict[str, Any] | None:
    user = get_user_by_username(conn, username)
    if not user or user["status"] != "active" or not user["password_hash"]:
        return None
    if not security.verify_password(user["password_hash"], password):
        return None
    if security.password_needs_rehash(user["password_hash"]):
        conn.execute(
            text("UPDATE app_user SET password_hash = :p WHERE id = :id"),
            {"p": security.hash_password(password), "id": user["id"]},
        )
    conn.execute(
        text("UPDATE app_user SET last_login_at = now() WHERE id = :id"), {"id": user["id"]}
    )
    user.pop("password_hash", None)
    return user


# --- sessions ---
def create_session(conn: Connection, user_id: UUID, ttl_hours: int) -> tuple[str, datetime]:
    token = security.generate_token()
    expires = datetime.now(UTC) + timedelta(hours=ttl_hours)
    conn.execute(
        text(
            "INSERT INTO session(app_user_id, token_hash, expires_at) "
            "VALUES (:u, :h, :e)"
        ),
        {"u": user_id, "h": security.hash_token(token), "e": expires},
    )
    return token, expires


def validate_session(conn: Connection, token: str) -> dict[str, Any] | None:
    row = conn.execute(
        text(
            "SELECT u.id, u.username, u.display_name, u.status, u.is_super_admin, s.id AS session_id "
            "FROM session s JOIN app_user u ON u.id = s.app_user_id "
            "WHERE s.token_hash = :h AND s.revoked_at IS NULL "
            "AND s.expires_at > now() AND u.status = 'active'"
        ),
        {"h": security.hash_token(token)},
    ).mappings().first()
    if not row:
        return None
    conn.execute(
        text("UPDATE session SET last_used_at = now() WHERE id = :id"),
        {"id": row["session_id"]},
    )
    return dict(row)


def revoke_session(conn: Connection, token: str) -> None:
    conn.execute(
        text(
            "UPDATE session SET revoked_at = now() "
            "WHERE token_hash = :h AND revoked_at IS NULL"
        ),
        {"h": security.hash_token(token)},
    )
