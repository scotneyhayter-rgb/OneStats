"""Phase 10, Stage 10.4: historical name & alias recognition.

``research_alias`` records historical name variants — former club/association names, abbreviations,
alternative spellings, newspaper transcription errors, historical place names — so a search can match
how a name actually appeared in the sources WITHOUT ever rewriting the original source text. An alias
may point at a known entity (club/competition/person/venue/team) or stand alone when the entity is not
yet in the system. The original wording is always retained; aliases only broaden matching.

Complements the existing organisation name history (deliverable 11); this table is research-facing and
covers free-form variants and transcription errors. Workspace-scoped (FORCE RLS); additive only.

Revision ID: 0044_research_alias
Revises: 0043_season_coverage
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0044_research_alias"
down_revision = "0043_season_coverage"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "research_alias",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),      # club|competition|grade|team|person|venue|place|other
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),   # the known entity, if any
        sa.Column("alias", sa.Text(), nullable=False),            # the variant as it appears historically
        sa.Column("normalised", sa.Text(), nullable=False),       # lower/trimmed, for matching
        sa.Column("alias_kind", sa.Text(), nullable=True),        # former_name|abbreviation|spelling|transcription|place
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "entity_type in ('club','competition','grade','team','person','venue','place','other')",
            name="research_alias_entity_type"),
        sa.UniqueConstraint("workspace_id", "entity_type", "entity_id", "normalised", name="uq_research_alias"),
    )
    op.create_index("ix_research_alias_norm", "research_alias", ["workspace_id", "normalised"])
    op.create_index("ix_research_alias_entity", "research_alias", ["workspace_id", "entity_type", "entity_id"])

    op.execute("ALTER TABLE research_alias ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE research_alias FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY research_alias_workspace_isolation ON research_alias "
               f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS research_alias_workspace_isolation ON research_alias")
    op.drop_table("research_alias")
