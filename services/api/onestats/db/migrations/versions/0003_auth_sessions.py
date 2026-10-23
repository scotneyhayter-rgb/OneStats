"""Phase 3 Stage 2: authentication fields, sessions, and system settings.

Adds password/auth columns to app_user, an opaque-token session table, and a small
system_setting key/value table (used for the one-time super-admin setup token hash).
These are global (not workspace-scoped) — no RLS. No cricket-domain tables.

Revision ID: 0003_auth_sessions
Revises: 0002_workspaces_rbac
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_auth_sessions"
down_revision = "0002_workspaces_rbac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_user", sa.Column("password_hash", sa.Text(), nullable=True))
    op.add_column(
        "app_user",
        sa.Column(
            "is_super_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "app_user", sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True)
    )

    op.create_table(
        "session",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), primary_key=True,
        ),
        sa.Column(
            "app_user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_session_token_hash"),
    )
    op.create_index("ix_session_app_user_id", "session", ["app_user_id"])

    op.create_table(
        "system_setting",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )


def downgrade() -> None:
    op.drop_table("system_setting")
    op.drop_index("ix_session_app_user_id", table_name="session")
    op.drop_table("session")
    op.drop_column("app_user", "last_login_at")
    op.drop_column("app_user", "is_super_admin")
    op.drop_column("app_user", "password_hash")
