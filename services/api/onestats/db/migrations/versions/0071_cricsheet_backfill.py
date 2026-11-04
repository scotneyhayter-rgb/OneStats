"""Cricsheet historical backfill state — resumable, controllable per format (Part G).

One row per (workspace, format) tracks a long-running backfill of the complete Cricsheet collection:
its status (pending/running/paused/completed/cancelled/failed), genuine progress counts, the last match
processed, and the bundle checksum (to notice a newly published bundle). Progress survives an app
restart because it lives here and in cricsheet_import_log; a resumed run skips matches already logged.

Workspace-scoped with FORCE RLS; additive only.

Revision ID: 0071_cricsheet_backfill
Revises: 0070_cricsheet_import_log
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0071_cricsheet_backfill"
down_revision = "0070_cricsheet_import_log"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "cricsheet_backfill",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("format", sa.Text(), nullable=False),              # test | odi | t20i
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("total_seen", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("processed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("imported", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_ref", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("bundle_sha256", sa.Text(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status in ('pending','running','paused','completed','cancelled','failed')",
                           name="cricsheet_backfill_status"),
        sa.CheckConstraint("format in ('test','odi','t20i')", name="cricsheet_backfill_format"),
        sa.UniqueConstraint("workspace_id", "format", name="uq_cricsheet_backfill_format"),
    )
    op.execute("ALTER TABLE cricsheet_backfill ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE cricsheet_backfill FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY cricsheet_backfill_workspace_isolation ON cricsheet_backfill "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS cricsheet_backfill_workspace_isolation ON cricsheet_backfill")
    op.drop_table("cricsheet_backfill")
