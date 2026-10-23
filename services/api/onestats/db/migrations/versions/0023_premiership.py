"""Phase 6 Stage 6: premierships & finals-series linkage.

Adds the premiership record on top of the existing finals-series structure (0011) and the match
classification model (0012/0018):

* ``premiership`` — a premiership for a competition/season/grade, with an explicit ``outcome``
  (awarded / shared / abandoned / not_awarded / unknown), an optional runner-up, the deciding
  series and/or match where applicable, a ``verification_status`` and source evidence. A
  premiership is **never** created automatically from a Grand Final result — it is an explicit,
  evidence-backed record (deliverable 14).
* ``premiership_team`` — the winning team(s); normally one row, two or more for a shared
  premiership. Kept as a child table so shared premierships are first-class, not a hack.

Also records each finals-series game's **relationship** within the series via a new
``finals_series_game.game_label`` column (e.g. ``semi_final``, ``grand_final``, ``replay``) — the
sequence was already ``game_number``. This is additive; existing rows get NULL (unknown).

Nothing is inferred: unknown stays unknown, corrections are audited, and the domain layer surfaces
consistency issues as warnings rather than rejecting historical records. Workspace-scoped with
FORCE RLS; governed by the existing ``competition.manage`` permission.

Revision ID: 0023_premiership
Revises: 0022_fall_of_wicket
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0023_premiership"
down_revision = "0022_fall_of_wicket"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"
_OUTCOMES = ("awarded", "shared", "abandoned", "not_awarded", "unknown")
_VERIFICATION = ("unverified", "provisional", "verified", "disputed")


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_workspace_isolation ON {table} "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def upgrade() -> None:
    op.add_column("finals_series_game", sa.Column("game_label", sa.Text(), nullable=True))

    op.create_table(
        "premiership",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("competition_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("competition.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("season.id", ondelete="SET NULL"), nullable=True),
        sa.Column("grade_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("grade.id", ondelete="SET NULL"), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("runner_up_team_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("team.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deciding_series_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("finals_series.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deciding_match_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("match.id", ondelete="SET NULL"), nullable=True),
        sa.Column("verification_status", sa.Text(), nullable=False, server_default=sa.text("'unverified'")),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("outcome IN (" + ", ".join(f"'{o}'" for o in _OUTCOMES) + ")",
                           name="premiership_outcome"),
        sa.CheckConstraint(
            "verification_status IN (" + ", ".join(f"'{v}'" for v in _VERIFICATION) + ")",
            name="premiership_verification_status"),
    )
    op.create_index("ix_premiership_competition", "premiership", ["competition_id"])
    # One premiership record per grade-season of a competition (where both are known). Shared
    # premierships are two winner rows on ONE record, not duplicate records.
    op.create_index("uq_premiership_scope", "premiership",
                    ["workspace_id", "competition_id", "season_id", "grade_id"], unique=True,
                    postgresql_where=sa.text("season_id IS NOT NULL AND grade_id IS NOT NULL"))
    _enable_rls("premiership")

    op.create_table(
        "premiership_team",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("premiership_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("premiership.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("team.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default=sa.text("'winner'")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("role IN ('winner','shared_winner')", name="premiership_team_role"),
        sa.UniqueConstraint("workspace_id", "premiership_id", "team_id", name="uq_premiership_team"),
    )
    op.create_index("ix_premiership_team_premiership", "premiership_team", ["premiership_id"])
    _enable_rls("premiership_team")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS premiership_team_workspace_isolation ON premiership_team")
    op.drop_table("premiership_team")
    op.execute("DROP POLICY IF EXISTS premiership_workspace_isolation ON premiership")
    op.drop_table("premiership")
    op.drop_column("finals_series_game", "game_label")
