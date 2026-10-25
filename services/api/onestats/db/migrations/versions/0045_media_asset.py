"""Phase 11, Stage 11.1: Media Archive — media assets + relationships.

``media_asset`` is OneStats' canonical media record. Its ``id`` is the **stable media identifier**:
links to matches, people, research evidence and heritage collections point at this id, never at a
storage location, so moving a file between providers never breaks a reference. Each asset records which
**storage provider** holds it (internal / onevault / external), the provider-specific **locator**, the
original file's **content type, size and SHA-256** (integrity), optional derivative references
(thumbnail/preview — the original is the preservation master and is never modified in place), and
copyright / licensing / attribution / provenance plus visibility and protection flags (private / junior
/ publication eligibility). OneStats works fully on the internal provider alone.

``media_link`` attaches an asset to any entity (match, person, research source, season, organisation,
team) — a single scalable link table rather than many special-purpose ones.

Workspace-scoped (FORCE RLS); additive only.

Revision ID: 0045_media_asset
Revises: 0044_research_alias
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0045_media_asset"
down_revision = "0044_research_alias"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "media_asset",
        # id IS the stable media identifier — storage-location independent
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("storage_provider", sa.Text(), nullable=False, server_default=sa.text("'internal'")),
        sa.Column("storage_locator", sa.Text(), nullable=True),   # internal filename / external URL / vault object id
        sa.Column("original_filename", sa.Text(), nullable=True),
        sa.Column("content_type", sa.Text(), nullable=True),
        sa.Column("file_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.Text(), nullable=True),            # integrity (NULL for external refs OneStats can't hash)
        sa.Column("kind", sa.Text(), nullable=False, server_default=sa.text("'document'")),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        # provenance / rights — internal access NEVER implies publication permission
        sa.Column("copyright_status", sa.Text(), nullable=True),
        sa.Column("licence", sa.Text(), nullable=True),
        sa.Column("attribution", sa.Text(), nullable=True),
        sa.Column("source_provenance", sa.Text(), nullable=True),
        # visibility / protection
        sa.Column("visibility", sa.Text(), nullable=False, server_default=sa.text("'workspace'")),
        sa.Column("publication_eligible", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sensitive", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("junior_protected", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        # derivatives (separate from the original master; original never modified in place)
        sa.Column("thumbnail_ref", sa.Text(), nullable=True),
        sa.Column("preview_ref", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("storage_provider in ('internal','onevault','external')", name="media_asset_provider"),
        sa.CheckConstraint("visibility in ('private','workspace','publishable')", name="media_asset_visibility"),
    )
    op.create_index("ix_media_asset_ws", "media_asset", ["workspace_id", "kind"])
    op.create_index("ix_media_asset_sha", "media_asset", ["workspace_id", "sha256"])

    op.create_table(
        "media_link",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_asset_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("media_asset.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),      # match|person|research_source|season|organisation|team|other
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "entity_type in ('match','person','research_source','season','organisation','team','other')",
            name="media_link_entity_type"),
        sa.UniqueConstraint("media_asset_id", "entity_type", "entity_id", name="uq_media_link"),
    )
    op.create_index("ix_media_link_entity", "media_link", ["workspace_id", "entity_type", "entity_id"])

    for tbl in ("media_asset", "media_link"):
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {tbl}_workspace_isolation ON {tbl} "
                   f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})")

    # --- permission: media.manage (granted to Super/Workspace Admin) ---
    op.execute(
        "INSERT INTO permission(key, description) "
        "VALUES ('media.manage', 'Upload, organise, migrate and curate media assets') "
        "ON CONFLICT (key) DO NOTHING"
    )
    op.execute(
        "INSERT INTO role_permission(role_id, permission_id) "
        "SELECT r.id, p.id FROM role r, permission p WHERE p.key = 'media.manage' "
        "AND r.workspace_id IS NULL AND r.key IN ('super_admin','workspace_admin') ON CONFLICT DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM role_permission WHERE permission_id IN (SELECT id FROM permission WHERE key = 'media.manage')")
    op.execute("DELETE FROM permission WHERE key = 'media.manage'")
    for tbl in ("media_link", "media_asset"):
        op.execute(f"DROP POLICY IF EXISTS {tbl}_workspace_isolation ON {tbl}")
        op.drop_table(tbl)
