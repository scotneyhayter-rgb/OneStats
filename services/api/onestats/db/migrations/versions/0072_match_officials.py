"""Match officials — umpires & scorers on a scorecard (Phase 6 extension).

A match can record the people who officiated it — umpires and scorers (plus TV/reserve umpires and a
match referee). Each official links to a canonical ``person`` so their appearances are the same identity
used everywhere else. Everything is explicit and recorded, never inferred; a match with no recorded
officials simply has none (unknown, not an assertion). Workspace-isolated under FORCE RLS, governed by
the existing ``match.manage`` permission, and cascaded with the match like every other scorecard child.

Revision ID: 0072_match_officials
Revises: 0071_cricsheet_backfill
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0072_match_officials"
down_revision = "0071_cricsheet_backfill"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"
_ROLES = "('umpire','scorer','tv_umpire','reserve_umpire','referee','other')"


def upgrade() -> None:
    op.create_table(
        "match_official",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("match_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("match.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("person.id", ondelete="SET NULL"), nullable=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(f"role IN {_ROLES}", name="match_official_role"),
        sa.UniqueConstraint("workspace_id", "match_id", "person_id", "role", name="uq_match_official"),
    )
    op.create_index("ix_match_official_match", "match_official", ["match_id"])
    op.execute("ALTER TABLE match_official ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE match_official FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY match_official_workspace_isolation ON match_official "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS match_official_workspace_isolation ON match_official")
    op.drop_table("match_official")
