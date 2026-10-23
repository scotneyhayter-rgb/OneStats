"""Phase 6 Stage 3: batting & dismissals.

One ``batting_entry`` row per batter per innings: batting order, player identity, runs, balls
faced, boundaries (and minutes where a source records them), and the full dismissal — type,
bowler and fielder attribution. The original CricketStatz ``Howout`` code is preserved verbatim
in ``dismissal_source_code`` and never overwritten by the mapped type; unresolved codes stay
unresolved (never guessed).

Unknown is not zero (deliverable 13.3): every statistic is nullable, so a partial or
newspaper-sourced card records only what is known. ``dismissal_type`` distinguishes the axes the
statistics engine needs (deliverable 16 §16.8): no innings (dnb/absent), not out
(not_out/retired_not_out), genuine dismissals (bowled/caught/.../run_out) and the unresolved
cases (retired/unknown/unknown_out). Duplicate batting entries are prevented per innings by
player identity and by batting position.

Workspace-scoped with FORCE RLS; governed by the existing ``match.manage`` permission.

Revision ID: 0020_batting_entry
Revises: 0019_innings
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020_batting_entry"
down_revision = "0019_innings"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"

# Canonical dismissal vocabulary (deliverable 16 §16.8). The original CS numeric code is kept
# separately in dismissal_source_code; unconfirmed/ambiguous CS codes map to 'retired',
# 'unknown' or 'unknown_out' and are flagged, never guessed.
_DISMISSAL_TYPES = (
    "dnb", "absent",                      # no innings
    "not_out", "retired_not_out",         # batted, not dismissed (not in average denominator)
    "bowled", "caught", "caught_behind", "caught_and_bowled", "lbw",
    "stumped", "hit_wicket",              # bowler-credit dismissals
    "run_out", "retired_out", "obstructing", "hit_twice", "timed_out",  # out, no bowler credit
    "unknown_out",                        # out, manner unknown (no bowler/fielder credit)
    "retired", "unknown",                 # unresolved status — never counted as a confirmed wicket
)


def upgrade() -> None:
    op.create_table(
        "batting_entry",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("innings_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("innings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("person.id", ondelete="SET NULL"), nullable=True),
        # batting order — nullable = unknown; no upper cap (team size is a playing condition)
        sa.Column("batting_position", sa.Integer(), nullable=True),
        # batting statistics — every value nullable = unknown (never defaulted to 0)
        sa.Column("runs", sa.Integer(), nullable=True),
        sa.Column("balls_faced", sa.Integer(), nullable=True),
        sa.Column("fours", sa.Integer(), nullable=True),
        sa.Column("sixes", sa.Integer(), nullable=True),
        sa.Column("minutes", sa.Integer(), nullable=True),
        # dismissal — mapped type plus the preserved original source code and attribution
        sa.Column("dismissal_type", sa.Text(), nullable=True),
        sa.Column("dismissal_source_code", sa.Text(), nullable=True),
        sa.Column("bowler_person_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("person.id", ondelete="SET NULL"), nullable=True),
        sa.Column("fielder_person_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("person.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("batting_position IS NULL OR batting_position >= 1",
                           name="batting_entry_position_positive"),
        sa.CheckConstraint("runs IS NULL OR runs >= 0", name="batting_entry_runs_nonneg"),
        sa.CheckConstraint("balls_faced IS NULL OR balls_faced >= 0", name="batting_entry_balls_nonneg"),
        sa.CheckConstraint("fours IS NULL OR fours >= 0", name="batting_entry_fours_nonneg"),
        sa.CheckConstraint("sixes IS NULL OR sixes >= 0", name="batting_entry_sixes_nonneg"),
        sa.CheckConstraint("minutes IS NULL OR minutes >= 0", name="batting_entry_minutes_nonneg"),
        sa.CheckConstraint(
            "dismissal_type IS NULL OR dismissal_type IN ("
            + ", ".join(f"'{d}'" for d in _DISMISSAL_TYPES) + ")",
            name="batting_entry_dismissal_type"),
    )
    op.create_index("ix_batting_entry_innings", "batting_entry", ["innings_id"])
    # Duplicate protection: a known player appears once per innings, and one batter per position.
    op.create_index("uq_batting_entry_person", "batting_entry",
                    ["workspace_id", "innings_id", "person_id"], unique=True,
                    postgresql_where=sa.text("person_id IS NOT NULL"))
    op.create_index("uq_batting_entry_position", "batting_entry",
                    ["workspace_id", "innings_id", "batting_position"], unique=True,
                    postgresql_where=sa.text("batting_position IS NOT NULL"))

    op.execute("ALTER TABLE batting_entry ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE batting_entry FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY batting_entry_workspace_isolation ON batting_entry "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS batting_entry_workspace_isolation ON batting_entry")
    op.drop_table("batting_entry")
