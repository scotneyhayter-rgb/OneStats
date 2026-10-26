"""Global administrative audit log for platform (Super-Admin) actions.

``audit_log`` is workspace-scoped (FORCE RLS, NOT NULL workspace_id), so it cannot record platform-level
user-management actions that happen without a workspace context. ``admin_audit`` is a small GLOBAL table
(like ``app_user``/``session``/``login_attempt``) for those actions — account create/suspend/reset/invite,
Super-Admin grant/revoke, recovery. No secrets are stored.

Revision ID: 0054_admin_audit
Revises: 0053_user_management
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0054_admin_audit"
down_revision = "0053_user_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("actor", sa.Text(), nullable=True),               # user id of the acting Super Admin (or 'recovery')
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
        sa.Column("at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_admin_audit_target", "admin_audit", ["target_user_id", "at"])


def downgrade() -> None:
    op.drop_table("admin_audit")
