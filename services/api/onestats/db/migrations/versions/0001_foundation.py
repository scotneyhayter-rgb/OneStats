"""Phase 2 foundation schema: workspace, app_user, audit_log + RLS scaffolding.

Foundation only — NO cricket-domain tables. Establishes the workspace-isolation pattern
(a workspace_id column + a Row-Level Security policy keyed on a per-session GUC) so domain
tables in later phases follow the same approach (deliverable 6). Runs as the
least-privilege onestats_app role, which owns the tables it creates.

Revision ID: 0001_foundation
Revises:
Create Date: 2026-10-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # workspace — the isolation boundary (deliverable 6).
    op.create_table(
        "workspace",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("short_name", sa.Text(), nullable=True),
        sa.Column(
            "type",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'club'"),
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "type in ('club','association','international','custom')",
            name="workspace_type",
        ),
    )

    # app_user — identity only. No password/auth here (no fake auth in Phase 2);
    # a real auth system is designed in later phases (deliverable 33).
    op.create_table(
        "app_user",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("username", name="uq_app_user_username"),
    )

    # audit_log — append-only, workspace-scoped; the RLS scaffold lives here.
    op.create_table(
        "audit_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspace.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("actor", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity", sa.Text(), nullable=True),
        sa.Column("entity_id", sa.Text(), nullable=True),
        sa.Column("before", postgresql.JSONB(), nullable=True),
        sa.Column("after", postgresql.JSONB(), nullable=True),
        sa.Column(
            "at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_audit_log_workspace_id", "audit_log", ["workspace_id"])

    # --- Row-Level Security scaffold (deliverable 6) ---
    # Policy keys off a per-session GUC `onestats.workspace_id`. The data-access layer
    # (later phase) sets it per request. Owners bypass RLS until FORCE is enabled during
    # Phase 3 hardening with the full data-access layer; enabling it now establishes the
    # pattern without risking lockout of this empty foundation database.
    op.execute("ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY audit_log_workspace_isolation ON audit_log
        USING (
            workspace_id = NULLIF(current_setting('onestats.workspace_id', true), '')::uuid
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS audit_log_workspace_isolation ON audit_log")
    op.drop_index("ix_audit_log_workspace_id", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("app_user")
    op.drop_table("workspace")
