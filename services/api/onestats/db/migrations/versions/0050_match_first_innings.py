"""Phase 12, Stage 12.12: multi-day first-innings result.

Multi-day competitions award points for the first-innings result as well as the outright result. The
outright result is already recorded (``result_type`` / ``won_by_team_id``); this adds
``first_innings_winner_team_id`` so a team ahead on first innings can be credited separately per the
competition's configured scheme (first_innings_win / first_innings_loss keys). Historical/limited-overs
matches simply leave it NULL. Additive; match is already workspace-scoped with FORCE RLS.

Revision ID: 0050_match_first_innings
Revises: 0049_saved_report
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0050_match_first_innings"
down_revision = "0049_saved_report"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("match", sa.Column("first_innings_winner_team_id", postgresql.UUID(as_uuid=True),
                                     sa.ForeignKey("team.id", ondelete="SET NULL"), nullable=True))


def downgrade() -> None:
    op.drop_column("match", "first_innings_winner_team_id")
