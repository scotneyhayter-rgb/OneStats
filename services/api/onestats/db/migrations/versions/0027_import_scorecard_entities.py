"""Phase 6 Stage 8b: CricketStatz scorecard import — widen staging entity vocabulary.

Reuses the existing staging tables (``import_batch`` / ``import_staging_record``) for the scorecard
body. One additive CHECK-constraint widening only — no new tables, no data reset, nothing dropped:

* ``import_staging_record.entity_type`` gains ``innings``, ``batting_entry``, ``bowling_entry`` and
  ``fall_of_wicket`` so the nested CricketStatz scorecard collections can be staged and promoted
  into the existing innings/batting/bowling/fall-of-wicket models.

Revision ID: 0027_import_scorecard_entities
Revises: 0026_partnership_origin
"""
from __future__ import annotations

from alembic import op

revision = "0027_import_scorecard_entities"
down_revision = "0026_partnership_origin"
branch_labels = None
depends_on = None

_ENTITY_OLD = "('club','team','venue','division','match','player','official')"
_ENTITY_NEW = ("('club','team','venue','division','match','player','official',"
               "'innings','batting_entry','bowling_entry','fall_of_wicket')")
_NAME = "ck_import_staging_record_import_staging_entity_type"


def _swap_check(values: str) -> None:
    op.execute(f"ALTER TABLE import_staging_record DROP CONSTRAINT IF EXISTS {_NAME}")
    op.execute(f"ALTER TABLE import_staging_record ADD CONSTRAINT {_NAME} CHECK (entity_type IN {values})")


def upgrade() -> None:
    _swap_check(_ENTITY_NEW)


def downgrade() -> None:
    # Safe only if no scorecard staging rows exist; harmless otherwise to leave the wider check.
    _swap_check(_ENTITY_OLD)
