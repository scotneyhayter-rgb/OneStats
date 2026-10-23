"""Transaction-scoped workspace context for Row-Level Security (deliverable 6, D2a).

Every workspace-scoped operation runs inside a transaction that first sets the per-session
GUC `onestats.workspace_id` with ``SET LOCAL`` (via ``set_config(..., is_local => true)``),
so PostgreSQL's FORCE RLS policies restrict reads and writes to that workspace. Because the
setting is transaction-local, it cannot leak between pooled connections or requests, and a
missing/empty value fails closed (no rows).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine


def set_workspace(conn: Connection, workspace_id: UUID | str) -> None:
    """Set the transaction-local workspace context on an open connection."""
    conn.execute(
        text("SELECT set_config('onestats.workspace_id', :wid, true)"),
        {"wid": str(workspace_id)},
    )


def set_user(conn: Connection, user_id: UUID | str) -> None:
    """Set the transaction-local user context (lets a user see their OWN memberships)."""
    conn.execute(
        text("SELECT set_config('onestats.user_id', :uid, true)"),
        {"uid": str(user_id)},
    )


@contextmanager
def workspace_transaction(
    engine: Engine, workspace_id: UUID | str, user_id: UUID | str | None = None
) -> Iterator[Connection]:
    """Open a transaction scoped to ``workspace_id`` (and optionally a user context);
    commit on success, rollback on error.

    Usage:
        with workspace_transaction(engine, ws_id) as conn:
            conn.execute(...)   # only this workspace's rows are visible/writable
    """
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            set_workspace(conn, workspace_id)
            if user_id is not None:
                set_user(conn, user_id)
            yield conn
            trans.commit()
        except Exception:
            trans.rollback()
            raise


@contextmanager
def user_transaction(engine: Engine, user_id: UUID | str) -> Iterator[Connection]:
    """Open a transaction with only the user context set (no workspace) — used to resolve
    the authenticated user's own cross-workspace memberships ("My Workspaces")."""
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            set_user(conn, user_id)
            yield conn
            trans.commit()
        except Exception:
            trans.rollback()
            raise
