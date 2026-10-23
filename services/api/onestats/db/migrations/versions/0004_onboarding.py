"""Phase 3 Stage 4: onboarding drafts, unique workspace identifier, membership self-view.

- `onboarding_draft`: a resumable, Super-Admin-owned onboarding wizard state (global).
- Unique `workspace.short_name` (the workspace's unique identifier) to prevent duplicates.
- Extend the app_user_workspace_role RLS policy so a user can see their OWN memberships
  across workspaces (for "My Workspaces"), via a new `onestats.user_id` context, while
  writes stay confined to the current workspace and others' memberships stay isolated.

Revision ID: 0004_onboarding
Revises: 0003_auth_sessions
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_onboarding"
down_revision = "0003_auth_sessions"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"
_USER = "NULLIF(current_setting('onestats.user_id', true), '')::uuid"


def upgrade() -> None:
    # Unique workspace identifier (slug). Partial unique allows NULL during drafting.
    op.create_index(
        "uq_workspace_short_name", "workspace", ["short_name"], unique=True,
        postgresql_where=sa.text("short_name IS NOT NULL"),
    )

    op.create_table(
        "onboarding_draft",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), primary_key=True,
        ),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "workspace_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspace.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("template", sa.Text(), nullable=True),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'in_progress'")),
        sa.Column("state", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status in ('in_progress','activated','abandoned')", name="onboarding_status"
        ),
    )

    # Extend membership visibility: own memberships visible across workspaces.
    op.execute(
        "DROP POLICY IF EXISTS app_user_workspace_role_workspace_isolation "
        "ON app_user_workspace_role"
    )
    op.execute(
        f"CREATE POLICY app_user_workspace_role_workspace_isolation "
        f"ON app_user_workspace_role "
        f"USING (workspace_id = {_WS} OR app_user_id = {_USER}) "
        f"WITH CHECK (workspace_id = {_WS})"
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS app_user_workspace_role_workspace_isolation "
        "ON app_user_workspace_role"
    )
    op.execute(
        f"CREATE POLICY app_user_workspace_role_workspace_isolation "
        f"ON app_user_workspace_role "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )
    op.drop_table("onboarding_draft")
    op.drop_index("uq_workspace_short_name", table_name="workspace")
