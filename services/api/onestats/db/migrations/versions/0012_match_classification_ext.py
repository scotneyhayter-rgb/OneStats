"""Phase 4 Stage 6 (revised): structured match-classification extension.

Extends the Stage 3 ``match_classification`` holder (migration 0007) — additively, not rewritten
— into the controlled vocabulary + unresolved-source registry for the revised classification
model: an explicit top-level ``category`` (home_away | final | grand_final | other |
unclassified), an optional ``finals_stage`` (qualifying/elimination/semi/preliminary/grand final
or custom), and a ``verified`` flag distinguishing confirmed classifications from unverified
imported candidates. Manually entered round labels never drive these; a missing classification is
``unclassified``, never Home & Away. Per-match assignment columns belong to the canonical match
table (Phase 8); this migration only extends the vocabulary/registry.

Revision ID: 0012_match_classification_ext
Revises: 0011_finals_series
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_match_classification_ext"
down_revision = "0011_finals_series"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("match_classification", sa.Column("category", sa.Text(), nullable=True))
    op.add_column("match_classification", sa.Column("finals_stage", sa.Text(), nullable=True))
    op.add_column(
        "match_classification",
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_check_constraint(
        "match_classification_category",
        "match_classification",
        "category IS NULL OR category IN "
        "('home_away','final','grand_final','other','unclassified')",
    )
    op.create_check_constraint(
        "match_classification_finals_stage",
        "match_classification",
        "finals_stage IS NULL OR finals_stage IN "
        "('qualifying_final','elimination_final','semi_final','preliminary_final',"
        "'grand_final','custom')",
    )


def downgrade() -> None:
    op.drop_constraint("match_classification_finals_stage", "match_classification", type_="check")
    op.drop_constraint("match_classification_category", "match_classification", type_="check")
    op.drop_column("match_classification", "verified")
    op.drop_column("match_classification", "finals_stage")
    op.drop_column("match_classification", "category")
