"""Role-based permission resolution and workspace membership (deliverable 7).

All queries assume the caller has already set the workspace context (the
`onestats.workspace_id` GUC) via the transaction-scoped data-access layer, so FORCE RLS
restricts membership/role rows to that workspace. The Super Administrator is global and
holds every permission in every workspace (checked by a flag, not by membership).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection


def builtin_role_id(conn: Connection, key: str) -> UUID | None:
    return conn.execute(
        text("SELECT id FROM role WHERE key = :k AND workspace_id IS NULL"),
        {"k": key},
    ).scalar_one_or_none()


def grant_role(conn: Connection, user_id: UUID, workspace_id: UUID, role_key: str) -> None:
    """Assign a built-in role to a user in the current workspace (idempotent).

    Requires the workspace context to be set (RLS WITH CHECK enforces workspace_id)."""
    # escalation guard: "super_admin" is a system-wide role (the app_user.is_super_admin flag), never a
    # workspace membership. A workspace/club admin must not be able to grant it via membership.
    if role_key == "super_admin":
        raise ValueError("cannot_grant_super_admin")
    role_id = builtin_role_id(conn, role_key)
    if role_id is None:
        raise ValueError(f"unknown_role:{role_key}")
    conn.execute(
        text(
            "INSERT INTO app_user_workspace_role(app_user_id, workspace_id, role_id) "
            "VALUES (:u, :w, :r) ON CONFLICT ON CONSTRAINT uq_membership DO NOTHING"
        ),
        {"u": user_id, "w": workspace_id, "r": role_id},
    )


def revoke_role(conn: Connection, user_id: UUID, workspace_id: UUID, role_key: str) -> None:
    conn.execute(
        text(
            "DELETE FROM app_user_workspace_role m USING role r "
            "WHERE m.role_id = r.id AND r.key = :k "
            "AND m.app_user_id = :u AND m.workspace_id = :w"
        ),
        {"k": role_key, "u": user_id, "w": workspace_id},
    )


def effective_permissions(
    conn: Connection, user_id: UUID, workspace_id: UUID, is_super_admin: bool
) -> set[str]:
    """The set of permission keys the user holds in this workspace."""
    if is_super_admin:
        rows = conn.execute(text("SELECT key FROM permission")).scalars().all()
        return set(rows)
    rows = conn.execute(
        text(
            "SELECT DISTINCT p.key "
            "FROM app_user_workspace_role m "
            "JOIN role_permission rp ON rp.role_id = m.role_id "
            "JOIN permission p ON p.id = rp.permission_id "
            "WHERE m.app_user_id = :u AND m.workspace_id = :w"
        ),
        {"u": user_id, "w": workspace_id},
    ).scalars().all()
    return set(rows)


def has_permission(
    conn: Connection,
    user_id: UUID,
    workspace_id: UUID,
    is_super_admin: bool,
    permission: str,
) -> bool:
    if is_super_admin:
        return True
    return permission in effective_permissions(conn, user_id, workspace_id, False)
