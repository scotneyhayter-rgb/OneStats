"""Phase 7 Stage 7.5: workspace-configurable match formats.

A workspace-scoped list of match formats (Test, First-Class, ODI, …, plus custom) that each
workspace administrator enables/disables and nominates a default from. Only ENABLED formats appear
in the normal Match Format dropdown. The match's ``format`` stays a free-text value, so a match
using a format later disabled, an imported source description, or a manual override is PRESERVED and
still displayed — disabling a format never deletes, hides or alters historical matches. Match format
is kept separate from the official statistical classification (``match.classification``).

Workspace-scoped with FORCE RLS; additive only.

Revision ID: 0031_match_formats
Revises: 0030_score_format
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0031_match_formats"
down_revision = "0030_score_format"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "match_format",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),           # stable slug (e.g. 't20', 'two_day')
        sa.Column("label", sa.Text(), nullable=False),          # display name
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("workspace_id", "code", name="uq_match_format_code"),
    )
    op.create_index("ix_match_format_workspace", "match_format", ["workspace_id"])
    # at most one default per workspace
    op.execute("CREATE UNIQUE INDEX uq_match_format_default ON match_format (workspace_id) WHERE is_default")
    op.execute("ALTER TABLE match_format ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE match_format FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY match_format_workspace_isolation ON match_format "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS match_format_workspace_isolation ON match_format")
    op.drop_table("match_format")
