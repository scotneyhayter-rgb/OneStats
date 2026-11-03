"""Internet Research Engine, Stage 1: persistent research jobs.

A ``research_job`` is one autonomous "Search the Internet" investigation: a natural-language subject
plus structured context (club / season / competition / match / player), run by an in-process background
worker. It carries status, JSONB progress and a resumable checkpoint, and a lease (owner + expiry) used
as a heartbeat so a job interrupted by a PC shutdown is never left falsely 'running' — on restart its
expired lease is reconciled and the job is requeued or failed. Modelled on Phase 9's ``sync_job`` but
decoupled from the AutoSync connector catalog, and with an explicit ``paused`` state the user controls.

A ``dedup_key`` (hash of the normalised query + context) with a partial unique index over active jobs
suppresses duplicate concurrent investigations of the same subject in a workspace (idempotency).

Workspace-scoped with FORCE RLS; additive only.

Revision ID: 0064_research_jobs
Revises: 0063_user_preference
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0064_research_jobs"
down_revision = "0063_user_preference"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"

# active = occupies a lease / counts against the duplicate-suppression index.
_ACTIVE = "('pending','running','paused','interrupted')"


def upgrade() -> None:
    op.create_table(
        "research_job",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),              # natural-language research subject
        sa.Column("depth", sa.Text(), nullable=False, server_default=sa.text("'standard'")),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("context", postgresql.JSONB(), nullable=True),    # club/season/competition/match/player
        sa.Column("dedup_key", sa.Text(), nullable=False),          # hash(normalised query + context)
        sa.Column("progress", postgresql.JSONB(), nullable=True),   # {phase, sources_examined, findings, ...}
        sa.Column("checkpoint", postgresql.JSONB(), nullable=True), # resume point (frontier/visited)
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
        sa.CheckConstraint(
            "status in ('pending','running','paused','succeeded','failed','cancelled','interrupted')",
            name="research_job_status"),
        sa.CheckConstraint("depth in ('quick','standard','deep')", name="research_job_depth"),
    )
    op.create_index("ix_research_job_ws_status", "research_job", ["workspace_id", "status"])
    op.create_index("ix_research_job_ws_created", "research_job", ["workspace_id", "created_at"])
    # At most one ACTIVE investigation per (workspace, dedup_key) — duplicate-job suppression.
    op.create_index("uq_research_job_active", "research_job", ["workspace_id", "dedup_key"],
                    unique=True, postgresql_where=sa.text(f"status in {_ACTIVE}"))
    op.execute("ALTER TABLE research_job ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE research_job FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY research_job_workspace_isolation ON research_job "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS research_job_workspace_isolation ON research_job")
    op.drop_table("research_job")
