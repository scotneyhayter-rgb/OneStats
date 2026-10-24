"""Phase 6 Stage 7: partnership origin & contribution model.

Additive, non-destructive columns on ``partnership`` (migration 0022) so a stand can record where
it came from (``origin``: calculated / manual / verified / unknown) and the per-batter contribution
detail (deliverable 25 foundation). Automatic FOW-derived partnerships are ``origin='calculated'``;
existing rows become ``'manual'`` (they were entered by hand). Every new field is nullable = unknown
(never zero, never fabricated). Strike rate / contribution % / run rate are DERIVED, not stored.

Revision ID: 0026_partnership_origin
Revises: 0025_affiliation_temporary
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026_partnership_origin"
down_revision = "0025_affiliation_temporary"
branch_labels = None
depends_on = None

_INT_COLS = ("runs_b1", "runs_b2", "extras", "balls_b1", "balls_b2", "balls_total",
             "fours_b1", "sixes_b1", "fours_b2", "sixes_b2")


def upgrade() -> None:
    op.add_column("partnership", sa.Column("origin", sa.Text(), nullable=False, server_default=sa.text("'manual'")))
    op.create_check_constraint(
        "partnership_origin", "partnership",
        "origin IN ('calculated','manual','verified','unknown')",
    )
    for c in _INT_COLS:
        op.add_column("partnership", sa.Column(c, sa.Integer(), nullable=True))
        op.create_check_constraint(f"partnership_{c}_nonneg", "partnership", f"{c} IS NULL OR {c} >= 0")
    op.add_column("partnership", sa.Column("confidence", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("partnership", "confidence")
    for c in reversed(_INT_COLS):
        op.drop_constraint(f"partnership_{c}_nonneg", "partnership", type_="check")
        op.drop_column("partnership", c)
    op.drop_constraint("partnership_origin", "partnership", type_="check")
    op.drop_column("partnership", "origin")
