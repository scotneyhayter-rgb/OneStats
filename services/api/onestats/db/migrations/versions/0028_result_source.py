"""Phase 7 Stage 7.3: match result provenance (automatic results & winning margins).

Additive only — no data reset, nothing dropped. Adds to ``match``:

* ``result_source`` — how the stored result was established: ``calculated`` (auto-derived from the
  scorecard), ``recorded`` (an official/imported result, e.g. a CricketStatz Result code),
  ``manual`` (an administrator override), or ``unknown``. Automatic recalculation only ever replaces
  a ``calculated`` or ``unknown`` result; ``recorded`` and ``manual`` results are preserved and a
  discrepancy with the calculated result is surfaced as a warning rather than silently overwritten.
* ``result_override_reason`` — the reason recorded when an administrator overrides the result.

Revision ID: 0028_result_source
Revises: 0027_import_scorecard_entities
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028_result_source"
down_revision = "0027_import_scorecard_entities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("match", sa.Column("result_source", sa.Text(), nullable=False,
                                     server_default=sa.text("'unknown'")))
    op.add_column("match", sa.Column("result_override_reason", sa.Text(), nullable=True))
    op.create_check_constraint(
        "match_result_source", "match",
        "result_source in ('calculated','recorded','manual','unknown')")
    # existing rows that already carry a result keep it, marked as 'recorded' (imported/entered);
    # rows with no result stay 'unknown'. Non-destructive.
    op.execute("UPDATE match SET result_source = 'recorded' "
               "WHERE result_type <> 'unknown' AND result_source = 'unknown'")


def downgrade() -> None:
    op.drop_constraint("match_result_source", "match", type_="check")
    op.drop_column("match", "result_override_reason")
    op.drop_column("match", "result_source")
