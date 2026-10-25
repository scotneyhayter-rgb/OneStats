"""Phase 9, Stage 9.2: AutoSync source registry.

A workspace's configured cricket information sources. Each row is one source instance (which code
connector, its endpoint/auth, declared coverage and formats, rate limits, reliability/health, last
successful access, connector version and field mapping). Credentials themselves are NOT stored here —
only a reference to secure storage. Workspace-scoped with FORCE RLS; additive only.

Revision ID: 0036_sync_source
Revises: 0035_sync_jobs
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0036_sync_source"
down_revision = "0035_sync_jobs"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "sync_source",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connector_id", sa.Text(), nullable=False),       # which code connector
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("access_method", sa.Text(), nullable=True),       # api | feed | file | fixture
        sa.Column("endpoint", sa.Text(), nullable=True),
        sa.Column("auth_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("credentials_ref", sa.Text(), nullable=True),     # secure-storage reference, NOT the secret
        sa.Column("countries", postgresql.JSONB(), nullable=True),
        sa.Column("formats", postgresql.JSONB(), nullable=True),
        sa.Column("coverage", postgresql.JSONB(), nullable=True),   # declared historical coverage etc.
        sa.Column("rate_limit", postgresql.JSONB(), nullable=True),
        sa.Column("reliability", sa.Text(), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("last_success_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("connector_version", sa.Text(), nullable=True),
        sa.Column("mapping", postgresql.JSONB(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("reliability in ('unknown','ok','degraded','down')", name="sync_source_reliability"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_sync_source_name"),
    )
    op.create_index("ix_sync_source_ws", "sync_source", ["workspace_id", "enabled"])
    op.execute("ALTER TABLE sync_source ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sync_source FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY sync_source_workspace_isolation ON sync_source "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS sync_source_workspace_isolation ON sync_source")
    op.drop_table("sync_source")
