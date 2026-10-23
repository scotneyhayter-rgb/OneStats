"""Phase 4 Stage 6 (revised): Finals Series foundation.

An explicit Finals Series entity so a multi-match final (best-of-three/five/custom) is modelled
distinctly from its individual matches and from a multi-day / multi-innings single match. A
Grand Final *series* (``is_grand_final_series``) is distinguishable from the individual Grand
Final *matches* that make it up. Ordered games link to matches by ``match_id`` (no FK yet — the
canonical match table is Phase 8, mirroring ``playing_condition.match_id``) and/or by
``match_source_ref`` so imported historical matches can be linked later without destructive
change. Supports series outcome states incl. drawn/tied/incomplete/abandoned/unresolved, which
underpins later Finals / Grand Final Series / Premiership reporting (one premiership per decided
series, never per game).

Workspace-scoped with FORCE RLS; governed by the existing ``competition.manage`` permission.

Revision ID: 0011_finals_series
Revises: 0010_import_staging
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_finals_series"
down_revision = "0010_import_staging"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"
_TABLES = ("finals_series", "finals_series_team", "finals_series_game")


def _ws_fk():
    return sa.Column(
        "workspace_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False,
    )


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_workspace_isolation ON {table} "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def upgrade() -> None:
    op.create_table(
        "finals_series",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        _ws_fk(),
        sa.Column("competition_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("competition.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("season.id", ondelete="SET NULL"), nullable=True),
        sa.Column("grade_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("grade.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("format", sa.Text(), nullable=False, server_default=sa.text("'single'")),
        sa.Column("is_grand_final_series", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("outcome", sa.Text(), nullable=False, server_default=sa.text("'unresolved'")),
        sa.Column("winner_team_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("team.id", ondelete="SET NULL"), nullable=True),
        sa.Column("outcome_notes", sa.Text(), nullable=True),
        sa.Column("rules", postgresql.JSONB(), nullable=True),   # historical series rules/evidence
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "format in ('single','best_of_3','best_of_5','custom')", name="finals_series_format"),
        sa.CheckConstraint(
            "outcome in ('in_progress','decided','drawn','tied','incomplete','abandoned','unresolved')",
            name="finals_series_outcome"),
    )
    op.create_index("ix_finals_series_workspace", "finals_series", ["workspace_id"])
    op.create_index("ix_finals_series_competition", "finals_series", ["competition_id"])

    op.create_table(
        "finals_series_team",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        _ws_fk(),
        sa.Column("series_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("finals_series.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("team.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seed_label", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("workspace_id", "series_id", "team_id", name="uq_finals_series_team"),
    )
    op.create_index("ix_finals_series_team_series", "finals_series_team", ["series_id"])

    op.create_table(
        "finals_series_game",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        _ws_fk(),
        sa.Column("series_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("finals_series.id", ondelete="CASCADE"), nullable=False),
        sa.Column("game_number", sa.Integer(), nullable=False),
        # match_id: no FK yet (canonical match table is Phase 8). match_source_ref lets an
        # imported historical match be linked now and resolved to match_id in Phase 8.
        sa.Column("match_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("match_source_ref", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("game_number >= 1", name="finals_series_game_number_positive"),
        sa.UniqueConstraint("workspace_id", "series_id", "game_number", name="uq_finals_series_game"),
    )
    op.create_index("ix_finals_series_game_series", "finals_series_game", ["series_id"])

    for tbl in _TABLES:
        _enable_rls(tbl)


def downgrade() -> None:
    for tbl in reversed(_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {tbl}_workspace_isolation ON {tbl}")
    for tbl in reversed(_TABLES):
        op.drop_table(tbl)
