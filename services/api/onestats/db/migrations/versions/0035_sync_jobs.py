"""Phase 9, Stage 9.1: AutoSync background jobs.

Persistent, workspace-scoped background jobs for scheduled/on-demand discovery. A job carries its
status, progress and a resumable checkpoint, plus a lease (owner + expiry) used as a heartbeat so a
job interrupted by a PC shutdown is NOT left falsely 'running': on restart its expired lease is
reconciled and the job is requeued or failed. A partial unique index prevents duplicate active jobs
for the same (workspace, source, kind).

Workspace-scoped with FORCE RLS; additive only.

Revision ID: 0035_sync_jobs
Revises: 0034_match_source
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0035_sync_jobs"
down_revision = "0034_match_source"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "sync_job",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),              # new|updated|historical|manual
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("schedule", sa.Text(), nullable=True),           # cron-like; null = on-demand
        sa.Column("next_run_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("progress", postgresql.JSONB(), nullable=True),
        sa.Column("checkpoint", postgresql.JSONB(), nullable=True),  # resume point
        sa.Column("lease_owner", sa.Text(), nullable=True),
        sa.Column("lease_expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint("status in ('pending','running','succeeded','failed','cancelled','interrupted')",
                           name="sync_job_status"),
        sa.CheckConstraint("kind in ('new','updated','historical','manual')", name="sync_job_kind"),
    )
    op.create_index("ix_sync_job_ws_status", "sync_job", ["workspace_id", "status"])
    op.create_index("ix_sync_job_due", "sync_job", ["status", "next_run_at"])
    # at most one ACTIVE (pending/running) job per source+kind in a workspace — duplicate prevention
    op.create_index("uq_sync_job_active", "sync_job", ["workspace_id", "source_system", "kind"],
                    unique=True, postgresql_where=sa.text("status in ('pending','running')"))
    op.execute("ALTER TABLE sync_job ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sync_job FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY sync_job_workspace_isolation ON sync_job "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS sync_job_workspace_isolation ON sync_job")
    op.drop_table("sync_job")
