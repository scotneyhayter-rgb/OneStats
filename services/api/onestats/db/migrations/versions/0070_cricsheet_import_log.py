"""Cricsheet import log — per-match import history, provenance and verification state (Parts F/G).

One row per Cricsheet match the workspace has attempted to import, carrying: the outcome
(awaiting_verification / skipped / failed), the exact file checksum (provenance + revised-file
detection), the source URL, and a link to the created match. This backs the Import Management UI's
progress and history, lets a re-run skip unchanged files, and records every attempt honestly.

Workspace-scoped with FORCE RLS; additive only.

Revision ID: 0070_cricsheet_import_log
Revises: 0069_match_home_away_known
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0070_cricsheet_import_log"
down_revision = "0069_match_home_away_known"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "cricsheet_import_log",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),          # Cricsheet match id
        sa.Column("format", sa.Text(), nullable=True),               # test | odi | t20i
        # awaiting_verification = imported, not yet approved; skipped = duplicate/unchanged/verified kept;
        # failed = parse/import error (detail says why)
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("match_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("match.id", ondelete="SET NULL"), nullable=True),
        sa.Column("content_sha256", sa.Text(), nullable=True),       # the exact file imported (provenance)
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("imported_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status in ('awaiting_verification','skipped','failed')",
                           name="cricsheet_import_log_status"),
        sa.UniqueConstraint("workspace_id", "source_ref", name="uq_cricsheet_import_log_ref"),
    )
    op.create_index("ix_cricsheet_import_log_ws", "cricsheet_import_log", ["workspace_id", "status"])
    op.execute("ALTER TABLE cricsheet_import_log ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE cricsheet_import_log FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY cricsheet_import_log_workspace_isolation ON cricsheet_import_log "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS cricsheet_import_log_workspace_isolation ON cricsheet_import_log")
    op.drop_table("cricsheet_import_log")
