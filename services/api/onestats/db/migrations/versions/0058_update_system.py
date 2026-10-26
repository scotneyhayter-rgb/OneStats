"""Update-system tables: system_state (maintenance mode) + update_event (audit trail).

System-level (not workspace-scoped), mirroring the global ``app_user`` table: no RLS, no
workspace_id. ``system_state`` is a single pinned row holding the server's maintenance flag and
message so a controlled server update can place the API into maintenance mode without new writes.
``update_event`` is an append-only audit trail of update lifecycle events (detected, backup,
migration, success/failure, recovery) — never storing secrets, tokens or connection strings.

Revision ID: 0058_update_system
Revises: 0057_dismissal_fielder
Create Date: 2026-10-26
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0058_update_system"
down_revision = "0057_dismissal_fielder"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Single-row server state (id is pinned to TRUE so there is exactly one row).
    op.create_table(
        "system_state",
        sa.Column("id", sa.Boolean(), primary_key=True, server_default=sa.text("true")),
        sa.Column("maintenance_mode", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("maintenance_message", sa.Text(), nullable=True),
        sa.Column("maintenance_since", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("maintenance_by", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("id = true", name="ck_system_state_single_row"),
    )
    op.execute("INSERT INTO system_state (id, maintenance_mode) VALUES (true, false)")

    # Append-only update lifecycle audit (system-wide; no secrets).
    op.create_table(
        "update_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("component", sa.Text(), nullable=False),           # desktop | server | database | release
        sa.Column("event", sa.Text(), nullable=False),               # detected | backup_validated | migration_started | success | failed | ...
        sa.Column("from_version", sa.Text(), nullable=True),
        sa.Column("to_version", sa.Text(), nullable=True),
        sa.Column("channel", sa.Text(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=True),              # ok | error | pending
        sa.Column("actor", sa.Text(), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=True),      # non-sensitive diagnostics only
        sa.Column("at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_update_event_at", "update_event", ["at"])
    op.create_index("ix_update_event_component", "update_event", ["component"])


def downgrade() -> None:
    op.drop_index("ix_update_event_component", table_name="update_event")
    op.drop_index("ix_update_event_at", table_name="update_event")
    op.drop_table("update_event")
    op.drop_table("system_state")
