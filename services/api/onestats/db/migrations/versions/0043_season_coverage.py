"""Phase 10, Stage 10.12: season coverage assessment for the Historical Research Timeline.

``season_coverage`` holds an explicit, evidence-backed coverage classification for a season (per the
optional competition/grade filter), set by a researcher. The timeline otherwise COMPUTES metrics from
real match data and will only ever show a computed class up to 'partial' / 'significant_gaps' /
'unassessed' — it never claims 'comprehensive' from counts alone (absence of a fixture list is
Unassessed, not Comprehensive). 'comprehensive' is reachable only through an explicit assessment here,
which carries the supporting-evidence note.

Workspace-scoped (FORCE RLS); additive only.

Revision ID: 0043_season_coverage
Revises: 0042_verification_states
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0043_season_coverage"
down_revision = "0042_verification_states"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "season_coverage",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("season.id", ondelete="CASCADE"), nullable=False),
        sa.Column("competition_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("competition.id", ondelete="SET NULL"), nullable=True),
        sa.Column("grade_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("grade.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assessed_class", sa.Text(), nullable=False),  # comprehensive|partial|significant_gaps|unassessed|inactive
        sa.Column("basis", sa.Text(), nullable=True),            # the evidence behind the assessment
        sa.Column("assessed_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "assessed_class in ('comprehensive','partial','significant_gaps','unassessed','inactive')",
            name="season_coverage_class"),
        sa.UniqueConstraint("workspace_id", "season_id", "competition_id", "grade_id", name="uq_season_coverage"),
    )
    op.create_index("ix_season_coverage_ws", "season_coverage", ["workspace_id", "season_id"])

    op.execute("ALTER TABLE season_coverage ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE season_coverage FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY season_coverage_workspace_isolation ON season_coverage "
               f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS season_coverage_workspace_isolation ON season_coverage")
    op.drop_table("season_coverage")
