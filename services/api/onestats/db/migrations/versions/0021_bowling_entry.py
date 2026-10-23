"""Phase 6 Stage 4: bowling.

One ``bowling_entry`` row per bowler per innings: bowler identity and order, overs, maidens,
runs conceded, wickets credited, and the wides/no-balls attributed to the bowler. The original
CricketStatz bowling-type code is preserved verbatim (``bowling_type_raw``) and unresolved codes
stay unresolved.

**Overs are never stored as a decimal.** The canonical figure is ``legal_balls`` — the underlying
count of legal deliveries — recorded only where evidence supports it. The original historical
notation is preserved separately in ``overs_text`` (e.g. ``'5.3'`` = 5 overs 3 balls, never 5.3 of
an over). Conversion between the two uses the match's ``balls_per_over`` playing condition
(Law 17), resolved at calculation time — never a hardcoded 6.

Unknown is not zero (deliverable 13.3): every figure is nullable. Wickets are the **recorded**
bowling figure; the engine separately derives bowler-credited wickets from the dismissal
attribution (Stage 3) and never auto-assigns a wicket where the dismissal is incomplete or
ambiguous. Recorded figures and calculated figures are kept distinct (deliverable 13.6).

Workspace-scoped with FORCE RLS; governed by the existing ``match.manage`` permission.

Revision ID: 0021_bowling_entry
Revises: 0020_batting_entry
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021_bowling_entry"
down_revision = "0020_batting_entry"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "bowling_entry",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("innings_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("innings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("person.id", ondelete="SET NULL"), nullable=True),
        # bowling order — nullable = unknown; no upper cap (team size is a playing condition)
        sa.Column("bowling_order", sa.Integer(), nullable=True),
        # overs — NEVER a decimal. overs_text keeps the original notation verbatim; legal_balls is
        # the canonical underlying legal-delivery count (nullable = unknown, not 0).
        sa.Column("overs_text", sa.Text(), nullable=True),
        sa.Column("legal_balls", sa.Integer(), nullable=True),
        sa.Column("maidens", sa.Integer(), nullable=True),
        sa.Column("runs_conceded", sa.Integer(), nullable=True),
        sa.Column("wickets", sa.Integer(), nullable=True),   # recorded figure (not auto-derived)
        sa.Column("wides", sa.Integer(), nullable=True),     # wides attributed to this bowler
        sa.Column("noballs", sa.Integer(), nullable=True),   # no-balls attributed to this bowler
        # source provenance — original CS bowling-type code preserved, mapping unresolved
        sa.Column("bowling_type_raw", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("bowling_order IS NULL OR bowling_order >= 1",
                           name="bowling_entry_order_positive"),
        sa.CheckConstraint("legal_balls IS NULL OR legal_balls >= 0", name="bowling_entry_balls_nonneg"),
        sa.CheckConstraint("maidens IS NULL OR maidens >= 0", name="bowling_entry_maidens_nonneg"),
        sa.CheckConstraint("runs_conceded IS NULL OR runs_conceded >= 0", name="bowling_entry_runs_nonneg"),
        sa.CheckConstraint("wickets IS NULL OR (wickets BETWEEN 0 AND 10)", name="bowling_entry_wickets_range"),
        sa.CheckConstraint("wides IS NULL OR wides >= 0", name="bowling_entry_wides_nonneg"),
        sa.CheckConstraint("noballs IS NULL OR noballs >= 0", name="bowling_entry_noballs_nonneg"),
    )
    op.create_index("ix_bowling_entry_innings", "bowling_entry", ["innings_id"])
    # Duplicate protection: a known bowler appears once per innings, and one entry per order slot.
    op.create_index("uq_bowling_entry_person", "bowling_entry",
                    ["workspace_id", "innings_id", "person_id"], unique=True,
                    postgresql_where=sa.text("person_id IS NOT NULL"))
    op.create_index("uq_bowling_entry_order", "bowling_entry",
                    ["workspace_id", "innings_id", "bowling_order"], unique=True,
                    postgresql_where=sa.text("bowling_order IS NOT NULL"))

    op.execute("ALTER TABLE bowling_entry ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE bowling_entry FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY bowling_entry_workspace_isolation ON bowling_entry "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS bowling_entry_workspace_isolation ON bowling_entry")
    op.drop_table("bowling_entry")
