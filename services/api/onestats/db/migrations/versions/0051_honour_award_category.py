"""Phase 13 (player profiles): free-form award category on honours.

Adds ``honour.award_category`` so club/association awards can carry any category the workspace uses
(Best & Fairest, Club Champion, Batting Award, Most Improved, Coach's Award, representative honours,
custom historical awards, …) — administrators create custom categories without schema changes. The
honour_type stays the high-level kind; award_category is the specific award. Additive.

Revision ID: 0051_honour_award_category
Revises: 0050_match_first_innings
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0051_honour_award_category"
down_revision = "0050_match_first_innings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("honour", sa.Column("award_category", sa.Text(), nullable=True))
    op.create_index("ix_honour_category", "honour", ["workspace_id", "award_category"])


def downgrade() -> None:
    op.drop_index("ix_honour_category", table_name="honour")
    op.drop_column("honour", "award_category")
