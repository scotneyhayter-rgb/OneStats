"""Phase 6 (Stage 7 Player Wizard): temporary affiliations.

Adds ``person_affiliation.is_temporary`` (additive, non-destructive) so a fill-in / guest
appearance can be recorded as a *temporary* association with the club a player represented in a
match — without changing their primary registration. Statistical attribution never depends on this
flag: a performance is attributed to the team actually represented in the match (the innings team),
so a temporary affiliation only aids roster suggestions, never the stats.

Revision ID: 0025_affiliation_temporary
Revises: 0024_toss_and_officials
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025_affiliation_temporary"
down_revision = "0024_toss_and_officials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "person_affiliation",
        sa.Column("is_temporary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("person_affiliation", "is_temporary")
