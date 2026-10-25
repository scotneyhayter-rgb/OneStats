"""Phase 11, Stage 11.7: optional Club Heritage Collection.

A curated set of media assets with historical significance markers and descriptions, suitable for
optional future website publication (Phase 29) — permission-controlled and never published by default.

* ``heritage_collection`` — a named curated collection (e.g. "RMCC Heritage").
* ``heritage_item`` — a curated entry referencing a media_asset, with a significance marker, description,
  display order and its own publication-eligibility flag (publication always stays an explicit decision).

Workspace-scoped (FORCE RLS); additive only.

Revision ID: 0046_heritage_collection
Revises: 0045_media_asset
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0046_heritage_collection"
down_revision = "0045_media_asset"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "heritage_collection",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_heritage_collection_ws", "heritage_collection", ["workspace_id"])

    op.create_table(
        "heritage_item",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("heritage_collection.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_asset_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("media_asset.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("significance", sa.Text(), nullable=True),   # historical significance marker
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("publication_eligible", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_heritage_item_collection", "heritage_item", ["collection_id", "display_order"])

    for tbl in ("heritage_item", "heritage_collection"):
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {tbl}_workspace_isolation ON {tbl} "
                   f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})")


def downgrade() -> None:
    for tbl in ("heritage_item", "heritage_collection"):
        op.execute(f"DROP POLICY IF EXISTS {tbl}_workspace_isolation ON {tbl}")
        op.drop_table(tbl)
