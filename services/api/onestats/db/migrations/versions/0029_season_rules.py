"""Phase 7 Stage 7.4: automatic season assignment — configurable season rules & provenance.

Additive only — no data reset, nothing dropped.

* ``competition.season_model`` — how a season is determined from a match date for this competition:
  ``au_summer`` (Australian summer spanning two years, e.g. 2019/20), ``calendar`` (Jan–Dec of one
  year), ``uk_summer`` (a single calendar-year summer), ``custom`` (use the competition's own season
  date ranges only), or ``unknown`` (no reliable rule — the season is left unresolved, never
  guessed). Defaults to ``unknown``.
* ``match.season_source`` — how the match's season was set: ``calculated`` (auto-assigned from the
  rule), ``manual`` (an administrator's choice — preserved, never overwritten), ``imported`` (from
  the source), or ``unknown``. Defaults to ``unknown``.

Revision ID: 0029_season_rules
Revises: 0028_result_source
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029_season_rules"
down_revision = "0028_result_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("competition", sa.Column("season_model", sa.Text(), nullable=False,
                                           server_default=sa.text("'unknown'")))
    op.create_check_constraint(
        "competition_season_model", "competition",
        "season_model in ('au_summer','calendar','uk_summer','custom','unknown')")
    op.add_column("match", sa.Column("season_source", sa.Text(), nullable=False,
                                     server_default=sa.text("'unknown'")))
    op.create_check_constraint(
        "match_season_source", "match",
        "season_source in ('calculated','manual','imported','unknown')")
    # existing matches that already have a season keep it, marked 'manual' so it is never overwritten.
    op.execute("UPDATE match SET season_source = 'manual' WHERE season_id IS NOT NULL AND season_source = 'unknown'")


def downgrade() -> None:
    op.drop_constraint("match_season_source", "match", type_="check")
    op.drop_column("match", "season_source")
    op.drop_constraint("competition_season_model", "competition", type_="check")
    op.drop_column("competition", "season_model")
