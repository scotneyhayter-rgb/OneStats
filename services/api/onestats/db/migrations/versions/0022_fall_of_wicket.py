"""Phase 6 Stage 5: fall of wicket & partnerships.

Two workspace-scoped tables nested under an innings:

* ``fall_of_wicket`` — one row per wicket that fell: wicket number, the team score at the fall,
  the dismissed batter and the not-out partner where known, the over at the fall (notation + legal
  balls), and a link back to the dismissed batter's ``batting_entry``. Everything but the keys is
  nullable = unknown (never 0).
* ``partnership`` — one row per batting partnership: the wicket it is for, runs/balls scored, the
  two participants, whether it was unbroken, and how it ended (``end_reason`` — wicket, retired,
  declared, …) so retirements and other unusual circumstances are recorded rather than forced into
  a wicket. Partnerships are intentionally **not** uniquely keyed by wicket number: a retirement
  can produce more than one stand for the same wicket, and the model must allow it.

Bowling partnerships (a OneStats statistical report over groups of 2–4 bowlers) are **not** stored
here and are not the same thing as a batting partnership; the existing ``bowling_entry`` +
dismissal attribution already carry the underlying data, and the records calculation is left to the
statistics phase (deliverable 25).

Data integrity: nothing is invented, unknown stays distinct from zero, incomplete historical cards
are allowed, and consistency issues are surfaced as warnings by the domain layer rather than
rejected here. Source values and evidence are preserved. FORCE RLS; governed by ``match.manage``.

Revision ID: 0022_fall_of_wicket
Revises: 0021_bowling_entry
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022_fall_of_wicket"
down_revision = "0021_bowling_entry"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"

_END_REASONS = ("wicket", "retired", "declared", "forfeited", "innings_closed", "unknown")


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_workspace_isolation ON {table} "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def upgrade() -> None:
    op.create_table(
        "fall_of_wicket",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("innings_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("innings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("wicket_number", sa.Integer(), nullable=True),
        sa.Column("team_score", sa.Integer(), nullable=True),
        sa.Column("dismissed_person_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("person.id", ondelete="SET NULL"), nullable=True),
        sa.Column("not_out_person_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("person.id", ondelete="SET NULL"), nullable=True),
        # link to the dismissed batter's scorecard row (relationship to batting records)
        sa.Column("batting_entry_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("batting_entry.id", ondelete="SET NULL"), nullable=True),
        # over at the fall — notation preserved verbatim, legal-ball count canonical (never decimal)
        sa.Column("overs_text", sa.Text(), nullable=True),
        sa.Column("legal_balls", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("wicket_number IS NULL OR wicket_number >= 1", name="fall_of_wicket_number_positive"),
        sa.CheckConstraint("team_score IS NULL OR team_score >= 0", name="fall_of_wicket_score_nonneg"),
        sa.CheckConstraint("legal_balls IS NULL OR legal_balls >= 0", name="fall_of_wicket_balls_nonneg"),
    )
    op.create_index("ix_fall_of_wicket_innings", "fall_of_wicket", ["innings_id"])
    # One fall per wicket number per innings (where the number is known).
    op.create_index("uq_fall_of_wicket_number", "fall_of_wicket",
                    ["workspace_id", "innings_id", "wicket_number"], unique=True,
                    postgresql_where=sa.text("wicket_number IS NOT NULL"))
    _enable_rls("fall_of_wicket")

    op.create_table(
        "partnership",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("innings_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("innings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("wicket_number", sa.Integer(), nullable=True),  # the Nth-wicket partnership
        sa.Column("runs", sa.Integer(), nullable=True),
        sa.Column("balls", sa.Integer(), nullable=True),
        sa.Column("player1_person_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("person.id", ondelete="SET NULL"), nullable=True),
        sa.Column("player2_person_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("person.id", ondelete="SET NULL"), nullable=True),
        sa.Column("unbroken", sa.Boolean(), nullable=True),  # NULL = unknown
        sa.Column("end_reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("wicket_number IS NULL OR wicket_number >= 1", name="partnership_wicket_positive"),
        sa.CheckConstraint("runs IS NULL OR runs >= 0", name="partnership_runs_nonneg"),
        sa.CheckConstraint("balls IS NULL OR balls >= 0", name="partnership_balls_nonneg"),
        sa.CheckConstraint(
            "end_reason IS NULL OR end_reason IN (" + ", ".join(f"'{r}'" for r in _END_REASONS) + ")",
            name="partnership_end_reason"),
        sa.CheckConstraint(
            "player1_person_id IS NULL OR player2_person_id IS NULL "
            "OR player1_person_id <> player2_person_id", name="partnership_players_differ"),
    )
    op.create_index("ix_partnership_innings", "partnership", ["innings_id"])
    _enable_rls("partnership")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS partnership_workspace_isolation ON partnership")
    op.drop_table("partnership")
    op.execute("DROP POLICY IF EXISTS fall_of_wicket_workspace_isolation ON fall_of_wicket")
    op.drop_table("fall_of_wicket")
