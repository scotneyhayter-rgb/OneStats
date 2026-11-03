"""Recurring scheduled tasks + genuine run history (International Men's Cricket, Part J).

A ``scheduled_task`` is a persistent, timezone-aware RECURRENCE DEFINITION (e.g. "every Saturday at
04:00 Australia/Melbourne"). It is deliberately separate from a one-shot ``sync_job``/``research_job``:
the task computes its next due time and, when due, ENQUEUES a job for the background worker to run. The
next due time is always recomputed in the task's IANA timezone (via ``zoneinfo``) so it is correct
across daylight-saving transitions — never by naive 7-day arithmetic.

``next_run_at``/``last_run_at`` are stored in UTC. Firing is an ATOMIC claim (conditional UPDATE on
``next_run_at <= now()``) so two worker ticks can never double-fire the same due task.

Honesty about "did it actually run": ``scheduled_task_run`` logs only real executions. It stores the
due time (``scheduled_for``) SEPARATELY from when the run actually happened (``ran_at``) and flags
``was_catch_up`` — so a run that fires late (because the PC was off at the scheduled time) is recorded
as a late catch-up, and the system NEVER claims a powered-off computer ran the job on time. A missed,
un-caught-up occurrence is simply absent; absence is not success.

Workspace-scoped with FORCE RLS; additive only.

Revision ID: 0067_scheduled_task
Revises: 0066_match_index
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0067_scheduled_task"
down_revision = "0066_match_index"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_workspace_isolation ON {table} "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def upgrade() -> None:
    op.create_table(
        "scheduled_task",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        # what the worker dispatches when this task fires (a registered dispatcher key)
        sa.Column("task_kind", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        # recurrence: weekly for now (extensible). Day-of-week is Python convention Monday=0 .. Sunday=6.
        sa.Column("schedule_kind", sa.Text(), nullable=False, server_default=sa.text("'weekly'")),
        sa.Column("timezone", sa.Text(), nullable=False),          # IANA, e.g. 'Australia/Melbourne'
        sa.Column("day_of_week", sa.Integer(), nullable=True),     # 0=Mon .. 6=Sun (weekly)
        sa.Column("hour", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("minute", sa.Integer(), nullable=False, server_default=sa.text("0")),
        # if a due occurrence is missed while the PC is off, fire it once (late) on next startup
        sa.Column("catch_up", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        # UTC instants
        sa.Column("next_run_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_status", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("schedule_kind in ('weekly')", name="scheduled_task_kind_schedule"),
        sa.CheckConstraint("day_of_week IS NULL OR (day_of_week BETWEEN 0 AND 6)",
                           name="scheduled_task_dow"),
        sa.CheckConstraint("hour BETWEEN 0 AND 23", name="scheduled_task_hour"),
        sa.CheckConstraint("minute BETWEEN 0 AND 59", name="scheduled_task_minute"),
        # one task of a given kind per workspace (the weekly intl update is a singleton)
        sa.UniqueConstraint("workspace_id", "task_kind", name="uq_scheduled_task_kind"),
    )
    op.create_index("ix_scheduled_task_due", "scheduled_task",
                    ["enabled", "paused", "next_run_at"])
    op.create_index("ix_scheduled_task_ws", "scheduled_task", ["workspace_id"])
    _enable_rls("scheduled_task")

    op.create_table(
        "scheduled_task_run",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("scheduled_task.id", ondelete="CASCADE"), nullable=False),
        # the due occurrence this run satisfies (in UTC) — kept SEPARATE from when it actually ran
        sa.Column("scheduled_for", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("ran_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        # true when this fired later than scheduled_for because the scheduled instant was missed
        sa.Column("was_catch_up", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        # the job this run enqueued (if any) — lets the UI link a run to its import job
        sa.Column("enqueued_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status in ('succeeded','failed','skipped','no_pipeline')",
            name="scheduled_task_run_status"),
    )
    op.create_index("ix_scheduled_task_run_task", "scheduled_task_run", ["task_id", "ran_at"])
    op.create_index("ix_scheduled_task_run_ws", "scheduled_task_run", ["workspace_id", "ran_at"])
    _enable_rls("scheduled_task_run")


def downgrade() -> None:
    for tbl in ("scheduled_task_run", "scheduled_task"):
        op.execute(f"DROP POLICY IF EXISTS {tbl}_workspace_isolation ON {tbl}")
        op.drop_table(tbl)
