"""Phase 5 Stage 5: CricketStatz player/official import — extend staging & role vocab.

Reuses the Phase 4 Stage 6 staging tables (``import_batch`` / ``import_staging_record``) for
player and official identity import. Two additive CHECK-constraint widenings only — no new tables,
no data reset:

* ``import_staging_record.entity_type`` gains ``player`` and ``official``.
* ``person_role.role`` gains ``official`` (CricketStatz officials are undifferentiated umpires/
  scorers; the generic ``official`` role preserves the player-vs-official distinction without
  inventing a specific sub-role).

Revision ID: 0017_people_import
Revises: 0016_player_profiles
"""
from __future__ import annotations

from alembic import op

revision = "0017_people_import"
down_revision = "0016_player_profiles"
branch_labels = None
depends_on = None

_ENTITY_OLD = "('club','team','venue','division','match')"
_ENTITY_NEW = "('club','team','venue','division','match','player','official')"
_ROLE_OLD = "('player','umpire','scorer','coach','administrator','selector','captain','other')"
_ROLE_NEW = "('player','umpire','scorer','coach','administrator','selector','captain','other','official')"


def _swap_check(table: str, name: str, column: str, values: str) -> None:
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
    op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({column} IN {values})")


def upgrade() -> None:
    _swap_check("import_staging_record", "ck_import_staging_record_import_staging_entity_type",
                "entity_type", _ENTITY_NEW)
    _swap_check("person_role", "ck_person_role_person_role_kind", "role", _ROLE_NEW)


def downgrade() -> None:
    # Safe only if no player/official rows exist; harmless otherwise to leave the wider check.
    _swap_check("import_staging_record", "ck_import_staging_record_import_staging_entity_type",
                "entity_type", _ENTITY_OLD)
    _swap_check("person_role", "ck_person_role_person_role_kind", "role", _ROLE_OLD)
