"""Multi-fielder run-outs (residual risk R-3) — additional involved fielders per dismissal.

A run-out often involves more than one fielder (e.g. a thrower plus whoever breaks the stumps). The primary
fielder stays on ``batting_entry.fielder_person_id`` (credited as a run-out, unchanged), while this table
records each **additional** involved fielder with a role. The statistics engine credits these as
``run_out_assists`` — a distinct, non-overlapping metric — so the primary ``run_outs`` figure is preserved,
the dismissal is still one wicket, and no involvement is invented. Workspace-isolated (FORCE RLS).

Revision ID: 0057_dismissal_fielder
Revises: 0056_upload_session
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0057_dismissal_fielder"
down_revision = "0056_upload_session"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"
_ROLES = ("assist", "thrower", "keeper", "fielder", "other")


def upgrade() -> None:
    op.create_table(
        "dismissal_fielder",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batting_entry_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("batting_entry.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("person.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default=sa.text("'assist'")),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("role IN (" + ", ".join(f"'{r}'" for r in _ROLES) + ")",
                           name="dismissal_fielder_role"),
        # one row per (dismissal, person): a fielder is credited at most once per dismissal
        sa.UniqueConstraint("batting_entry_id", "person_id", name="uq_dismissal_fielder"),
    )
    op.create_index("ix_dismissal_fielder_entry", "dismissal_fielder", ["batting_entry_id"])

    op.execute("ALTER TABLE dismissal_fielder ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE dismissal_fielder FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY dismissal_fielder_workspace_isolation ON dismissal_fielder "
               f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS dismissal_fielder_workspace_isolation ON dismissal_fielder")
    op.drop_table("dismissal_fielder")
