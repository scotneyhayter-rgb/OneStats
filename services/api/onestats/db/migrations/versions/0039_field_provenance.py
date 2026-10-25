"""Phase 10, Stage 10.9: field-level historical provenance.

``field_provenance`` records, for each material historical fact of a match, which source(s) support
which value — the heart of multi-source reconstruction and conflict handling. One row per
(match, field_path, source): the source's original wording (``claimed_value``), the normalised value,
an evidence status and optional confidence, the researcher who entered it, and the verification
decision. Rows are **retained** when superseded or rejected (the full claim history is preserved), and
the key is deliberately stable (match + field path + source) so provenance survives match updates,
player merges, imports and recalculations.

A scalable single table, not a proliferation of per-field tables. Workspace-scoped (FORCE RLS);
additive only.

Revision ID: 0039_field_provenance
Revises: 0038_research_centre
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0039_field_provenance"
down_revision = "0038_research_centre"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "field_provenance",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("match_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("match.id", ondelete="CASCADE"), nullable=False),
        # stable, human-readable path, e.g. 'match.result', 'match.date',
        # 'batting.<team>.<player_or_position>.runs', 'bowling.<team>.<player>.wickets'
        sa.Column("field_path", sa.Text(), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("research_source.id", ondelete="SET NULL"), nullable=True),
        sa.Column("claimed_value", sa.Text(), nullable=True),       # the source's own wording (verbatim)
        sa.Column("normalised_value", sa.Text(), nullable=True),    # OneStats-normalised value (NULL = unknown)
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'claimed'")),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("researcher", sa.Text(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("superseded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status in ('claimed','accepted','rejected','superseded')", name="field_provenance_status"),
        # one claim per source per field; re-recording updates in place (claims stay traceable)
        sa.UniqueConstraint("match_id", "field_path", "source_id", name="uq_field_provenance"),
    )
    op.create_index("ix_field_provenance_match", "field_provenance", ["match_id", "field_path"])
    op.create_index("ix_field_provenance_ws", "field_provenance", ["workspace_id"])

    op.execute("ALTER TABLE field_provenance ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE field_provenance FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY field_provenance_workspace_isolation ON field_provenance "
               f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS field_provenance_workspace_isolation ON field_provenance")
    op.drop_table("field_provenance")
