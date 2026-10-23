"""Cross-workspace isolation tests (Phase 3, requirement 10).

Proves that, operating as the least-privilege onestats_app role under FORCE RLS, a session
scoped to one workspace cannot READ or WRITE another workspace's rows. Requires a live
database; skipped automatically when no credential is configured. Everything runs inside a
single transaction that is rolled back — no data persists.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from onestats.core.config import get_settings
from onestats.db.workspace import set_workspace

settings = get_settings()
pytestmark = pytest.mark.skipif(
    not settings.db_configured, reason="no live database credential configured"
)


@pytest.fixture
def engine():
    eng = create_engine(settings.database_url, future=True)
    yield eng
    eng.dispose()


def _new_workspace(conn, name: str):
    return conn.execute(
        text("INSERT INTO workspace(name, type) VALUES (:n, 'club') RETURNING id"),
        {"n": name},
    ).scalar_one()


def test_audit_rows_are_isolated_by_workspace(engine):
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            ws_a = _new_workspace(conn, "ISO A")
            ws_b = _new_workspace(conn, "ISO B")

            # Write an audit row in workspace A's context.
            set_workspace(conn, ws_a)
            conn.execute(
                text("INSERT INTO audit_log(workspace_id, action) VALUES (:w, 'a')"),
                {"w": ws_a},
            )
            visible_a = conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one()
            assert visible_a == 1, "workspace A should see its own row"

            # Switch to workspace B: A's row must be invisible (isolation on READ).
            set_workspace(conn, ws_b)
            visible_b = conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one()
            assert visible_b == 0, "workspace B must NOT see workspace A's row"
        finally:
            trans.rollback()


def test_cannot_write_into_another_workspace(engine):
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            ws_a = _new_workspace(conn, "ISO A2")
            ws_b = _new_workspace(conn, "ISO B2")

            # Context = B, but attempt to insert a row tagged for A → RLS WITH CHECK denies.
            set_workspace(conn, ws_b)
            sp = conn.begin_nested()
            with pytest.raises((ProgrammingError, DBAPIError)):
                conn.execute(
                    text("INSERT INTO audit_log(workspace_id, action) VALUES (:w, 'x')"),
                    {"w": ws_a},
                )
            sp.rollback()
        finally:
            trans.rollback()


def test_no_workspace_context_sees_nothing(engine):
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            ws = _new_workspace(conn, "ISO C")
            set_workspace(conn, ws)
            conn.execute(
                text("INSERT INTO audit_log(workspace_id, action) VALUES (:w, 'c')"),
                {"w": ws},
            )
            # Clear the workspace context → fail-closed (no rows visible).
            conn.execute(text("SELECT set_config('onestats.workspace_id', '', true)"))
            count = conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one()
            assert count == 0, "with no workspace context, no audit rows are visible"
        finally:
            trans.rollback()
