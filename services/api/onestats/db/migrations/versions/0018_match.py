"""Phase 6 Stage 1: match core, classification & results.

The canonical ``match`` (fixture header) and ``match_team`` (home/away sides, captain/keeper),
with explicit, configurable classification that is **independent of the manually entered round**
label (round is stored verbatim and never determines classification; a missing classification is
``unclassified``, never Home & Away). Results use an explicit vocabulary with nullable margins;
CricketStatz raw values are preserved and unresolved ones stay unresolved. Statistical inclusion
is owned by OneStats (``include_in_statistics``).

This migration also RESOLVES the reserved match hooks from earlier phases: ``playing_condition``
and ``finals_series_game`` gain real foreign keys to ``match`` (both tables are empty, so this is
additive and safe). Adds the ``match.manage`` permission. No scorecard body yet (later stages);
no statistics compute (Phase 7). All workspace-scoped with FORCE RLS.

Revision ID: 0018_match
Revises: 0017_people_import
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018_match"
down_revision = "0017_people_import"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_workspace_isolation ON {table} "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def upgrade() -> None:
    op.create_table(
        "match",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("competition_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("competition.id", ondelete="SET NULL"), nullable=True),
        sa.Column("grade_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("grade.id", ondelete="SET NULL"), nullable=True),
        sa.Column("season_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("season.id", ondelete="SET NULL"), nullable=True),
        sa.Column("venue_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("venue.id", ondelete="SET NULL"), nullable=True),
        sa.Column("match_date", sa.Date(), nullable=True),  # unknown stays NULL
        sa.Column("date_precision", sa.Text(), nullable=False, server_default=sa.text("'exact'")),
        sa.Column("round", sa.Text(), nullable=True),   # verbatim; NEVER classifies a match
        sa.Column("matchtype", sa.Text(), nullable=True),  # 1 innings/2 innings/T20 etc.
        sa.Column("format", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'draft'")),
        # explicit, independently editable classification (Phase 4 vocabulary)
        sa.Column("classification", sa.Text(), nullable=False, server_default=sa.text("'unclassified'")),
        sa.Column("finals_stage", sa.Text(), nullable=True),
        sa.Column("classification_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("classification_ref_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("match_classification.id", ondelete="SET NULL"), nullable=True),
        # result
        sa.Column("result_type", sa.Text(), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("result_raw", sa.Text(), nullable=True),   # preserve CricketStatz Result code etc.
        sa.Column("won_by_team_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("team.id", ondelete="SET NULL"), nullable=True),
        sa.Column("margin_runs", sa.Integer(), nullable=True),
        sa.Column("margin_wickets", sa.Integer(), nullable=True),
        sa.Column("include_in_statistics", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("date_precision in ('unknown','exact','year','month','approx')", name="match_date_precision"),
        sa.CheckConstraint("status in ('draft','final','abandoned')", name="match_status"),
        sa.CheckConstraint(
            "classification in ('home_away','final','grand_final','other','unclassified')",
            name="match_classification_category"),
        sa.CheckConstraint(
            "finals_stage IS NULL OR finals_stage IN "
            "('qualifying_final','elimination_final','semi_final','preliminary_final','grand_final','custom')",
            name="match_finals_stage"),
        sa.CheckConstraint(
            "result_type in ('home_win','away_win','tie','draw','no_result','abandoned','washout','forfeit','unknown')",
            name="match_result_type"),
        sa.CheckConstraint("margin_runs IS NULL OR margin_runs >= 0", name="match_margin_runs"),
        sa.CheckConstraint("margin_wickets IS NULL OR (margin_wickets BETWEEN 0 AND 10)", name="match_margin_wickets"),
    )
    op.create_index("ix_match_workspace", "match", ["workspace_id"])
    op.create_index("ix_match_competition", "match", ["competition_id"])
    op.create_index("ix_match_season", "match", ["season_id"])
    op.create_index("ix_match_date", "match", ["match_date"])

    op.create_table(
        "match_team",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("match_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("match.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("team.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_home", sa.Boolean(), nullable=False),
        sa.Column("captain_person_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("person.id", ondelete="SET NULL"), nullable=True),
        sa.Column("wicketkeeper_person_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("person.id", ondelete="SET NULL"), nullable=True),
        sa.Column("bonus_points", sa.Numeric(6, 2), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("workspace_id", "match_id", "team_id", name="uq_match_team"),
    )
    op.create_index("ix_match_team_match", "match_team", ["match_id"])
    # at most one home side and one away side per match
    op.create_index("uq_match_team_side", "match_team", ["workspace_id", "match_id", "is_home"], unique=True)

    _enable_rls("match")
    _enable_rls("match_team")

    # --- resolve the reserved match_id hooks from earlier phases (tables are empty) ---
    op.create_foreign_key("fk_playing_condition_match_id_match", "playing_condition", "match",
                          ["match_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_finals_series_game_match_id_match", "finals_series_game", "match",
                          ["match_id"], ["id"], ondelete="SET NULL")

    # --- permission: match.manage ---
    op.execute(
        "INSERT INTO permission(key, description) "
        "VALUES ('match.manage', 'Manage matches and enter/correct scorecards') "
        "ON CONFLICT (key) DO NOTHING"
    )
    op.execute(
        "INSERT INTO role_permission(role_id, permission_id) "
        "SELECT r.id, p.id FROM role r, permission p "
        "WHERE p.key = 'match.manage' "
        "AND r.workspace_id IS NULL AND r.key IN ('super_admin','workspace_admin') "
        "ON CONFLICT DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permission WHERE permission_id IN "
        "(SELECT id FROM permission WHERE key = 'match.manage')"
    )
    op.execute("DELETE FROM permission WHERE key = 'match.manage'")
    op.drop_constraint("fk_finals_series_game_match_id_match", "finals_series_game", type_="foreignkey")
    op.drop_constraint("fk_playing_condition_match_id_match", "playing_condition", type_="foreignkey")
    for tbl in ("match_team", "match"):
        op.execute(f"DROP POLICY IF EXISTS {tbl}_workspace_isolation ON {tbl}")
    op.drop_table("match_team")
    op.drop_table("match")
