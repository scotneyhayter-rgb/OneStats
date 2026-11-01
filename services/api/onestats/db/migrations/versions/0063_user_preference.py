"""Per-user (optionally per-workspace) preferences, e.g. dashboard customisation (Part 15).

A single JSONB bag per (user, workspace?, namespace). Row-Level Security keys on the per-request
``onestats.user_id`` context so a user can only ever read/write their OWN preferences — this is
user-owned metadata, not workspace content, so it is scoped by user rather than by workspace.
No cricket data; nothing here affects statistics.

Revision ID: 0063_user_preference
Revises: 0062_role_grant_reconcile
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0063_user_preference"
down_revision = "0062_role_grant_reconcile"
branch_labels = None
depends_on = None

_USER = "NULLIF(current_setting('onestats.user_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "user_preference",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("app_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=True),
        sa.Column("namespace", sa.Text(), nullable=False),
        sa.Column("prefs", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    # one row per (user, namespace) globally, and one per (user, workspace, namespace) scoped
    op.create_index("uq_user_pref_global", "user_preference", ["app_user_id", "namespace"],
                    unique=True, postgresql_where=sa.text("workspace_id IS NULL"))
    op.create_index("uq_user_pref_ws", "user_preference", ["app_user_id", "workspace_id", "namespace"],
                    unique=True, postgresql_where=sa.text("workspace_id IS NOT NULL"))

    op.execute("ALTER TABLE user_preference ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE user_preference FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY user_preference_owner ON user_preference "
        f"USING (app_user_id = {_USER}) WITH CHECK (app_user_id = {_USER})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS user_preference_owner ON user_preference")
    op.drop_index("uq_user_pref_ws", table_name="user_preference")
    op.drop_index("uq_user_pref_global", table_name="user_preference")
    op.drop_table("user_preference")
