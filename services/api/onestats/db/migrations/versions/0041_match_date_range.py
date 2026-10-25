"""Phase 10, Stage 10.7: historical date uncertainty on matches.

Extends the match date model so historical reconstructions can retain genuine date uncertainty
(deliverable 19 §16; Phase 10 §10.3) without ever faking precision:

* ``date_precision`` gains ``range`` (a span between two dates) and ``season`` (season only) alongside
  the existing exact / year / month / approx / unknown.
* ``match_date_end`` (nullable) stores the end of a date range; ``match_date`` is its start.

Additive and backward-compatible (widens a CHECK, adds a nullable column). The match table is already
workspace-scoped with FORCE RLS.

Revision ID: 0041_match_date_range
Revises: 0040_source_extraction
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041_match_date_range"
down_revision = "0040_source_extraction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("match", sa.Column("match_date_end", sa.Date(), nullable=True))
    op.drop_constraint("match_date_precision", "match", type_="check")
    op.create_check_constraint(
        "match_date_precision", "match",
        "date_precision in ('unknown','exact','year','month','approx','range','season')",
    )


def downgrade() -> None:
    op.drop_constraint("match_date_precision", "match", type_="check")
    op.create_check_constraint(
        "match_date_precision", "match",
        "date_precision in ('unknown','exact','year','month','approx')",
    )
    op.drop_column("match", "match_date_end")
