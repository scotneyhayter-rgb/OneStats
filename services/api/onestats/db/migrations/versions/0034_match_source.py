"""Phase 8, Stage 8.5: multiple historical sources per match (R1).

A match may be described by more than one source — different exports, or different newspaper editions
of the same fixture. ``match_source`` records each contributing source against a canonical match: its
source system/ref, checksum, optional edition label, and the source's own field values
(``recorded_fields``). This preserves source-specific evidence and lets conflicting accounts be
surfaced for administrator review — attaching a source NEVER overwrites the approved scorecard.

Idempotent: unique on (match, source_system, source_ref), so re-importing the same source re-attaches
in place. Workspace-scoped with FORCE RLS; additive only.

Revision ID: 0034_match_source
Revises: 0033_stat_contributions
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0034_match_source"
down_revision = "0033_stat_contributions"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "match_source",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("match_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("match.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("source_filename", sa.Text(), nullable=True),
        sa.Column("source_sha256", sa.Text(), nullable=True),
        sa.Column("edition", sa.Text(), nullable=True),               # e.g. a newspaper edition label
        sa.Column("recorded_fields", postgresql.JSONB(), nullable=True),   # the source's own values
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("match_id", "source_system", "source_ref", name="uq_match_source"),
    )
    op.create_index("ix_match_source_match", "match_source", ["match_id"])
    op.create_index("ix_match_source_lookup", "match_source", ["workspace_id", "source_system", "source_ref"])
    op.execute("ALTER TABLE match_source ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE match_source FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY match_source_workspace_isolation ON match_source "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS match_source_workspace_isolation ON match_source")
    op.drop_table("match_source")
