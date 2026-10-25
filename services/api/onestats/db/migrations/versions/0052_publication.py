"""Phase 15: website publishing — publications + public snapshots.

``publication`` is a hosting-neutral record that a report or public player profile has been published: it
holds the report/profile reference, the saved filters, a permanent unguessable ``slug``, a status
(published/unpublished/revoked), and the last successfully published **snapshot** (rendered data + HTML +
checksum + branding) so public access works from the snapshot alone — offline-capable and never touching
the live admin database. The same snapshot feeds static export (upload to existing hosting) or a future
central OneStats publishing service; neither approach is baked in.

RLS: management is workspace-scoped (FORCE RLS). SELECT additionally exposes rows whose status is
``published`` so the public read path (no workspace context) can resolve a snapshot by slug; INSERT/UPDATE/
DELETE remain confined to the owning workspace. Snapshots contain only approved, publication-eligible data
(no DOB/junior/private), so public exposure is intended.

Revision ID: 0052_publication
Revises: 0051_honour_award_category
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0052_publication"
down_revision = "0051_honour_award_category"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "publication",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),                 # 'report' | 'player_profile'
        sa.Column("report_id", sa.Text(), nullable=True),             # catalogue report id (kind='report')
        sa.Column("person_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("person.id", ondelete="CASCADE"), nullable=True),  # kind='player_profile'
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("filters", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'published'")),
        sa.Column("stale", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        # last successfully published snapshot (offline-capable public source of truth)
        sa.Column("snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("snapshot_html", sa.Text(), nullable=True),
        sa.Column("checksum", sa.Text(), nullable=True),
        sa.Column("snapshot_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("kind IN ('report','player_profile')", name="publication_kind"),
        sa.CheckConstraint("status IN ('published','unpublished','revoked')", name="publication_status"),
        sa.UniqueConstraint("slug", name="uq_publication_slug"),
    )
    op.create_index("ix_publication_ws", "publication", ["workspace_id", "status"])

    op.execute("ALTER TABLE publication ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE publication FORCE ROW LEVEL SECURITY")
    # SELECT: own workspace (any status) OR any published row (public read by slug, no workspace context).
    op.execute(f"CREATE POLICY publication_select ON publication FOR SELECT "
               f"USING (workspace_id = {_WS} OR status = 'published')")
    # Writes are confined to the owning workspace.
    op.execute(f"CREATE POLICY publication_insert ON publication FOR INSERT WITH CHECK (workspace_id = {_WS})")
    op.execute(f"CREATE POLICY publication_update ON publication FOR UPDATE "
               f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})")
    op.execute(f"CREATE POLICY publication_delete ON publication FOR DELETE USING (workspace_id = {_WS})")


def downgrade() -> None:
    for pol in ("publication_select", "publication_insert", "publication_update", "publication_delete"):
        op.execute(f"DROP POLICY IF EXISTS {pol} ON publication")
    op.drop_table("publication")
