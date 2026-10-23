"""Phase 4 Stage 4: playing conditions & historical rules.

Captures the rules a match is played under, configurable per competition, season, grade and
match, and versioned by scope so historical rules are never applied retroactively across all
seasons. Every structured field is nullable — **unknown stays unknown**, never defaulted (so a
later audit engine won't treat a gap as an error).

``playing_condition`` (one row per scope target, enforced by partial unique indexes):

* ``scope`` = competition | season | grade | match, with the matching FK populated.
  ``match_id`` has no FK yet (the matches table arrives in a later phase); the resolution order
  is match → grade → season → competition.
* Structured core (all nullable = unknown): ``overs_limit``, ``max_players`` (team size —
  configurable, never hard-coded), ``balls_per_over``, ``innings_per_side``, ``format``.
* ``points`` JSONB (nullable) — the competition points scheme (win/draw/tie/bonus, etc.), which
  varies too much historically for fixed columns.
* ``extra`` JSONB — any other controlled rule extensions (D33).

Workspace-scoped with FORCE RLS. Governed by the existing ``competition.manage`` permission.

Revision ID: 0008_playing_conditions
Revises: 0007_competitions
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_playing_conditions"
down_revision = "0007_competitions"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "playing_condition",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("competition_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("competition.id", ondelete="CASCADE"), nullable=True),
        sa.Column("season_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("season.id", ondelete="CASCADE"), nullable=True),
        sa.Column("grade_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("grade.id", ondelete="CASCADE"), nullable=True),
        # match_id carries no FK yet — the matches table is introduced in a later phase.
        sa.Column("match_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Structured core — nullable = unknown (never defaulted).
        sa.Column("overs_limit", sa.Integer(), nullable=True),
        sa.Column("max_players", sa.Integer(), nullable=True),
        sa.Column("balls_per_over", sa.Integer(), nullable=True),
        sa.Column("innings_per_side", sa.Integer(), nullable=True),
        sa.Column("format", sa.Text(), nullable=True),
        sa.Column("points", postgresql.JSONB(), nullable=True),
        sa.Column("extra", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("scope in ('competition','season','grade','match')", name="playing_condition_scope"),
        # Positive-only where known (unknown stays NULL and is allowed).
        sa.CheckConstraint("overs_limit IS NULL OR overs_limit > 0", name="pc_overs_positive"),
        sa.CheckConstraint("max_players IS NULL OR max_players > 0", name="pc_max_players_positive"),
        sa.CheckConstraint("balls_per_over IS NULL OR balls_per_over > 0", name="pc_bpo_positive"),
        sa.CheckConstraint("innings_per_side IS NULL OR innings_per_side > 0", name="pc_innings_positive"),
        # The FK matching the scope must be populated.
        sa.CheckConstraint(
            "(scope = 'competition' AND competition_id IS NOT NULL) "
            "OR (scope = 'season' AND season_id IS NOT NULL) "
            "OR (scope = 'grade' AND grade_id IS NOT NULL) "
            "OR (scope = 'match' AND match_id IS NOT NULL)",
            name="playing_condition_scope_target",
        ),
    )
    op.create_index("ix_playing_condition_workspace", "playing_condition", ["workspace_id"])
    op.create_index("ix_playing_condition_competition", "playing_condition", ["competition_id"])
    op.create_index("ix_playing_condition_season", "playing_condition", ["season_id"])
    op.create_index("ix_playing_condition_grade", "playing_condition", ["grade_id"])
    # One condition row per scope target (keeps resolution unambiguous; supports upsert).
    op.create_index("uq_pc_competition", "playing_condition", ["workspace_id", "competition_id"],
                    unique=True, postgresql_where=sa.text("scope = 'competition'"))
    op.create_index("uq_pc_season", "playing_condition", ["workspace_id", "season_id"],
                    unique=True, postgresql_where=sa.text("scope = 'season'"))
    op.create_index("uq_pc_grade", "playing_condition", ["workspace_id", "grade_id"],
                    unique=True, postgresql_where=sa.text("scope = 'grade'"))
    op.create_index("uq_pc_match", "playing_condition", ["workspace_id", "match_id"],
                    unique=True, postgresql_where=sa.text("scope = 'match'"))

    op.execute("ALTER TABLE playing_condition ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE playing_condition FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY playing_condition_workspace_isolation ON playing_condition "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS playing_condition_workspace_isolation ON playing_condition")
    op.drop_table("playing_condition")
