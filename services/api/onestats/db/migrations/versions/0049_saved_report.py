"""Phase 12, Stage 12.17: saved Report Builder configurations.

``saved_report`` persists a report definition (report key + filters/sort/thresholds in ``config``) so a
user can reopen, edit or delete it. A report may be private to its owner or shared within the workspace
(read-only to others). The config holds only report parameters — no private data — so sharing a
definition never exposes restricted records. Saved reports run through the same deterministic engine as
standard reports.

Workspace-scoped (FORCE RLS); additive only.

Revision ID: 0049_saved_report
Revises: 0048_honours
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0049_saved_report"
down_revision = "0048_honours"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "saved_report",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("report", sa.Text(), nullable=False),            # report key (batting, bowling, ...)
        sa.Column("config", postgresql.JSONB(), nullable=True),    # filters/order_by/thresholds (parameters only)
        sa.Column("shared", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("workspace_id", "created_by", "name", name="uq_saved_report_name"),
    )
    op.create_index("ix_saved_report_ws", "saved_report", ["workspace_id", "shared"])

    op.execute("ALTER TABLE saved_report ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE saved_report FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY saved_report_workspace_isolation ON saved_report "
               f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS saved_report_workspace_isolation ON saved_report")
    op.drop_table("saved_report")
