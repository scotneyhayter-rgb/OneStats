"""Phase 10, Stage 10.6: OCR / text-extraction pipeline.

``source_extraction`` holds, per source document (and page), the machine-extracted OCR text, the
researcher-corrected transcription, and the method/version/confidence used. These are kept as distinct
layers so OCR output is never mistaken for verified truth:

  original image (research_source.file_ref) -> machine OCR (ocr_text) ->
  researcher-corrected transcription (corrected_text) -> structured data (field_provenance) ->
  verified facts (match approval)

Workspace-scoped (FORCE RLS); additive only.

Revision ID: 0040_source_extraction
Revises: 0039_field_provenance
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0040_source_extraction"
down_revision = "0039_field_provenance"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "source_extraction",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("research_source.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("method", sa.Text(), nullable=False, server_default=sa.text("'none'")),  # tesseract|manual|none
        sa.Column("method_version", sa.Text(), nullable=True),
        sa.Column("ocr_text", sa.Text(), nullable=True),          # machine output — preserved, never edited in place
        sa.Column("corrected_text", sa.Text(), nullable=True),    # researcher-corrected transcription
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status in ('pending','done','failed','manual')", name="source_extraction_status"),
        sa.UniqueConstraint("source_id", "page", name="uq_source_extraction_page"),
    )
    op.create_index("ix_source_extraction_source", "source_extraction", ["source_id"])
    op.create_index("ix_source_extraction_ws", "source_extraction", ["workspace_id"])

    op.execute("ALTER TABLE source_extraction ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE source_extraction FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY source_extraction_workspace_isolation ON source_extraction "
               f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS source_extraction_workspace_isolation ON source_extraction")
    op.drop_table("source_extraction")
