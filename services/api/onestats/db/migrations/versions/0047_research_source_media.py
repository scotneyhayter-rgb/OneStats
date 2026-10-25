"""Phase 11, Stage 11.9: link Phase 10 research sources to the media archive.

Adds ``research_source.media_asset_id`` so a research source document can be promoted into a single
canonical ``media_asset`` (one file, one media record) rather than living in a separate, parallel media
library. Promotion MOVES the file into the media store (checksum-verified) and points the research
source at the asset — no duplicate files or records.

Additive; the research_source table is already workspace-scoped with FORCE RLS.

Revision ID: 0047_research_source_media
Revises: 0046_heritage_collection
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0047_research_source_media"
down_revision = "0046_heritage_collection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("research_source",
                  sa.Column("media_asset_id", postgresql.UUID(as_uuid=True),
                            sa.ForeignKey("media_asset.id", ondelete="SET NULL"), nullable=True))


def downgrade() -> None:
    op.drop_column("research_source", "media_asset_id")
