"""Phase 7 Stage 7.7: workspace score-display format (Australian vs English).

Additive only. Adds ``workspace.score_format`` — the default way innings scores are shown across the
workspace: ``au`` (wickets/runs, e.g. 10/127) or ``en`` (runs/wickets, e.g. 127/10). This is display
formatting ONLY; runs and wickets remain stored separately and are never altered by it. An individual
user may override the workspace default in their own client (per-viewer preference).

Revision ID: 0030_score_format
Revises: 0029_season_rules
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030_score_format"
down_revision = "0029_season_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workspace", sa.Column("score_format", sa.Text(), nullable=False,
                                         server_default=sa.text("'au'")))
    op.create_check_constraint("workspace_score_format", "workspace", "score_format in ('au','en')")


def downgrade() -> None:
    op.drop_constraint("workspace_score_format", "workspace", type_="check")
    op.drop_column("workspace", "score_format")
