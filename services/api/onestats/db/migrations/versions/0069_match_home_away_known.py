"""Add match.home_away_known so an unknown home/away can be stored honestly.

Some sources (e.g. Cricsheet for internationals) do not record which side was at home. The ``match_team``
table requires exactly one home and one away row, so there is no way to say "unknown" there. This adds a
match-level flag, defaulting TRUE (every existing match keeps its current home/away meaning). When it is
FALSE, the statistics engine treats home/away as unknown and excludes the match from home/away splits,
rather than trusting an assumed side.

Revision ID: 0069_match_home_away_known
Revises: 0068_scheduled_task_daily
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0069_match_home_away_known"
down_revision = "0068_scheduled_task_daily"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("match", sa.Column("home_away_known", sa.Boolean(), nullable=False,
                                     server_default=sa.text("true")))


def downgrade() -> None:
    op.drop_column("match", "home_away_known")
