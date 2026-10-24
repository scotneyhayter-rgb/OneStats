"""Phase 6 (Stage 7 review): toss, acting captains and a second wicketkeeper.

Additive, non-destructive columns on the existing ``match`` and ``match_team`` tables — no data is
moved or dropped:

* ``match.toss_winner_team_id`` + ``match.toss_decision`` — record the toss explicitly. The toss is
  NEVER inferred from the batting order; both stay NULL/unknown unless recorded, and the decision
  vocabulary includes ``no_toss`` and ``not_recorded`` so those historical facts are distinct from
  an unrecorded blank.
* ``match_team.acting_captain_person_id`` — an acting/replacement captain alongside the substantive
  ``captain_person_id`` (match-specific).
* ``match_team.wicketkeeper2_person_id`` — a second/replacement keeper alongside
  ``wicketkeeper_person_id`` (mirrors the CricketStatz ``homekeeper2``/``awaykeeper2`` fields).

Everything is nullable = unknown (never zero, never a confirmed fact). Workspace isolation,
permissions, audit and provenance are unchanged. Governed by the existing ``match.manage``.

Revision ID: 0024_toss_and_officials
Revises: 0023_premiership
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0024_toss_and_officials"
down_revision = "0023_premiership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("match", sa.Column("toss_winner_team_id", postgresql.UUID(as_uuid=True),
                                     sa.ForeignKey("team.id", ondelete="SET NULL"), nullable=True))
    op.add_column("match", sa.Column("toss_decision", sa.Text(), nullable=True))
    op.create_check_constraint(
        "match_toss_decision", "match",
        "toss_decision IS NULL OR toss_decision IN ('bat','field','no_toss','not_recorded','unknown')",
    )
    op.add_column("match_team", sa.Column("acting_captain_person_id", postgresql.UUID(as_uuid=True),
                                          sa.ForeignKey("person.id", ondelete="SET NULL"), nullable=True))
    op.add_column("match_team", sa.Column("wicketkeeper2_person_id", postgresql.UUID(as_uuid=True),
                                          sa.ForeignKey("person.id", ondelete="SET NULL"), nullable=True))


def downgrade() -> None:
    op.drop_column("match_team", "wicketkeeper2_person_id")
    op.drop_column("match_team", "acting_captain_person_id")
    op.drop_constraint("match_toss_decision", "match", type_="check")
    op.drop_column("match", "toss_decision")
    op.drop_column("match", "toss_winner_team_id")
