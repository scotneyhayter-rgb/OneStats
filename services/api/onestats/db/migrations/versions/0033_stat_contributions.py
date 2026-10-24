"""Phase 7 Stage 7.8: automatic recalculation framework — official statistics ledger.

A per-match contributions ledger (``match_stat_contribution``) that is the authoritative source for
OFFICIAL statistics. A match's contributions are computed and stored only while it is an approved,
statistics-eligible scorecard; recomputing a match REPLACES its rows (idempotent, no double
counting). Because the ledger is written at approval time and not by later edits, official
statistics keep the last approved version until a revision is re-approved. Deleting a match (e.g. a
duplicate) removes its contributions via ON DELETE CASCADE.

Each row is one subject's (person/team) contribution to one match for one calculator, with the
figures in ``metrics`` (jsonb) and the match's season/grade/competition for scoped aggregation.
Future statistics/records/milestones/points/AutoSync register more calculators against this table.

Workspace-scoped with FORCE RLS; additive only.

Revision ID: 0033_stat_contributions
Revises: 0032_scorecard_approval
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0033_stat_contributions"
down_revision = "0032_scorecard_approval"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "match_stat_contribution",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("match_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("match.id", ondelete="CASCADE"), nullable=False),
        sa.Column("calculator", sa.Text(), nullable=False),            # e.g. 'player_batting'
        sa.Column("subject_kind", sa.Text(), nullable=False),          # 'person' | 'team'
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("season_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("grade_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("competition_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("subject_kind in ('person','team')", name="stat_contribution_subject_kind"),
        sa.UniqueConstraint("match_id", "calculator", "subject_kind", "subject_id",
                            name="uq_stat_contribution"),
    )
    op.create_index("ix_stat_contribution_subject", "match_stat_contribution",
                    ["workspace_id", "calculator", "subject_id"])
    op.create_index("ix_stat_contribution_match", "match_stat_contribution", ["match_id"])
    op.execute("ALTER TABLE match_stat_contribution ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE match_stat_contribution FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY stat_contribution_workspace_isolation ON match_stat_contribution "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS stat_contribution_workspace_isolation ON match_stat_contribution")
    op.drop_table("match_stat_contribution")
