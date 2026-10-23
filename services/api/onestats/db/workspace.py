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


@contextmanager
def workspace_transaction(engine: Engine, workspace_id: UUID | str) -> Iterator[Connection]:
    """Open a transaction scoped to ``workspace_id``; commit on success, rollback on error.

    Usage:
        with workspace_transaction(engine, ws_id) as conn:
            conn.execute(...)   # only this workspace's rows are visible/writable
    """
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            set_workspace(conn, workspace_id)
            yield conn
            trans.commit()
        except Exception:
            trans.rollback()
            raise
