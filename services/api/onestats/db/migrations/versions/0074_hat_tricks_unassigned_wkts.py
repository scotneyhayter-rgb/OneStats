"""Record hat-tricks per bowler and run-outs / unassigned wickets per innings.

Two recording-only additions that mirror CricketStatz's bowling card:

* ``bowling_entry.hat_tricks`` — the number of hat-tricks a bowler took in the innings (a wicket
  with the two preceding deliveries also taking wickets). It is recorded, never derived from the
  ball-by-ball data OneStats does not hold. NULL means unknown (not zero).
* ``innings.unassigned_wickets`` — wickets that fell but are not credited to any bowler (run-outs
  and other non-bowler dismissals). Together with the bowlers' recorded wickets this reconciles to
  the innings wickets fallen. NULL means unknown (not zero).

Both are nullable integers; existing rows stay unknown. No historical figure is changed.

Revision ID: 0074_hat_tricks_unassigned_wkts
Revises: 0073_workspace_public_base_url
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0074_hat_tricks_unassigned_wkts"
down_revision = "0073_workspace_public_base_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bowling_entry", sa.Column("hat_tricks", sa.Integer(), nullable=True))
    op.add_column("innings", sa.Column("unassigned_wickets", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("innings", "unassigned_wickets")
    op.drop_column("bowling_entry", "hat_tricks")
