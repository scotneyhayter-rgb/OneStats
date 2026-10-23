"""Phase 6 Stage 2: innings & extras.

Each innings of a match (multiple per match), with the batting/bowling sides, status
(in_progress/completed/declared/closed/forfeited/incomplete/unknown), all five extras
(byes/leg byes/wides/no-balls/penalty) and the CricketStatz ``iresult`` preserved raw with an
unresolved mapping (the legend is not confirmed — never guessed).

Totals are kept as distinct concepts (deliverable 13): **source** values (extras here; batting
runs and bowling-conceded runs arrive with those scorecard stages) feed a **derived** total, and
an optional **official override** (total/wickets) is stored separately with reason, evidence,
approving user and timestamp — it never overwrites the original scorecard. Every scalar is
nullable = unknown; missing historical data never becomes zero.

Workspace-scoped with FORCE RLS; governed by the existing ``match.manage`` permission.

Revision ID: 0019_innings
Revises: 0018_match
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0019_innings"
down_revision = "0018_match"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "innings",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("match_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("match.id", ondelete="CASCADE"), nullable=False),
        sa.Column("inns_number", sa.Integer(), nullable=False),
        sa.Column("batting_team_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("team.id", ondelete="SET NULL"), nullable=True),
        sa.Column("bowling_team_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("team.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'unknown'")),
        # extras — nullable = unknown (never defaulted to 0)
        sa.Column("byes", sa.Integer(), nullable=True),
        sa.Column("legbyes", sa.Integer(), nullable=True),
        sa.Column("wides", sa.Integer(), nullable=True),
        sa.Column("noballs", sa.Integer(), nullable=True),
        sa.Column("penalty", sa.Integer(), nullable=True),
        # optional official override (kept distinct from source; never overwrites the scorecard)
        sa.Column("official_total", sa.Integer(), nullable=True),
        sa.Column("official_wickets", sa.Integer(), nullable=True),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("override_evidence", sa.Text(), nullable=True),
        sa.Column("override_by", sa.Text(), nullable=True),
        sa.Column("override_at", sa.TIMESTAMP(timezone=True), nullable=True),
        # source provenance
        sa.Column("iresult_raw", sa.Text(), nullable=True),
        sa.Column("iresult", sa.Text(), nullable=True),
        sa.Column("iresult_status", sa.Text(), nullable=False, server_default=sa.text("'unresolved'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("inns_number >= 1", name="innings_number_positive"),
        sa.CheckConstraint(
            "status in ('in_progress','completed','declared','closed','forfeited','incomplete','unknown')",
            name="innings_status"),
        sa.CheckConstraint("iresult_status in ('confirmed','unresolved')", name="innings_iresult_status"),
        sa.CheckConstraint("byes IS NULL OR byes >= 0", name="innings_byes_nonneg"),
        sa.CheckConstraint("legbyes IS NULL OR legbyes >= 0", name="innings_legbyes_nonneg"),
        sa.CheckConstraint("wides IS NULL OR wides >= 0", name="innings_wides_nonneg"),
        sa.CheckConstraint("noballs IS NULL OR noballs >= 0", name="innings_noballs_nonneg"),
        sa.CheckConstraint("penalty IS NULL OR penalty >= 0", name="innings_penalty_nonneg"),
        sa.CheckConstraint("official_total IS NULL OR official_total >= 0", name="innings_official_total_nonneg"),
        sa.CheckConstraint("official_wickets IS NULL OR (official_wickets BETWEEN 0 AND 10)",
                           name="innings_official_wickets_range"),
        sa.CheckConstraint("batting_team_id IS NULL OR bowling_team_id IS NULL OR batting_team_id <> bowling_team_id",
                           name="innings_teams_differ"),
        sa.UniqueConstraint("workspace_id", "match_id", "inns_number", name="uq_innings_number"),
    )
    op.create_index("ix_innings_match", "innings", ["match_id"])

    op.execute("ALTER TABLE innings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE innings FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY innings_workspace_isolation ON innings "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS innings_workspace_isolation ON innings")
    op.drop_table("innings")
