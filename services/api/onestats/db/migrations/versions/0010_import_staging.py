"""Phase 4 Stage 6: Cricket Statz structural import — staging & batches.

A staging-first import: source rows are parsed into ``import_staging_record`` under an
``import_batch``, validated and previewed, and only promoted into the canonical Phase 1-5
tables on explicit administrator approval. Nothing here touches canonical data; promotion is
performed by the domain layer and is idempotent (source_ref), reversible (rollback) and
audited. No match scorecards (Phase 8); matches are staged structurally only.

Both tables are workspace-scoped with FORCE RLS. Adds the ``import.manage`` permission.

Revision ID: 0010_import_staging
Revises: 0009_org_relationships
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_import_staging"
down_revision = "0009_org_relationships"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_workspace_isolation ON {table} "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def upgrade() -> None:
    op.create_table(
        "import_batch",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=False, server_default=sa.text("'cricket_statz'")),
        sa.Column("source_filename", sa.Text(), nullable=True),
        sa.Column("source_sha256", sa.Text(), nullable=True),  # content hash for re-import detection
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'staged'")),
        sa.Column("counts", postgresql.JSONB(), nullable=True),  # per-entity staged/new/matched/unresolved/error
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("promoted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("promoted_by", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status in ('staged','validated','previewed','promoting','promoted',"
            "'partially_promoted','cancelled','failed')",
            name="import_batch_status",
        ),
    )
    op.create_index("ix_import_batch_workspace", "import_batch", ["workspace_id"])

    op.create_table(
        "import_staging_record",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("import_batch.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),  # club|team|venue|division|match
        sa.Column("source_ref", sa.Text(), nullable=False),   # original CS id (verbatim)
        sa.Column("raw", postgresql.JSONB(), nullable=False),      # verbatim source row (never altered)
        sa.Column("normalised", postgresql.JSONB(), nullable=True),  # sentinel-aware mapped values
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'staged'")),
        # resolution: new (will create) | matched (existing by source_ref) | unresolved (needs admin)
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("matched_canonical_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("issues", postgresql.JSONB(), nullable=True),  # unresolved/ambiguity/error flags preserved
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "entity_type in ('club','team','venue','division','match')",
            name="import_staging_entity_type",
        ),
        sa.CheckConstraint(
            "status in ('staged','duplicate','unresolved','promoted','skipped','error')",
            name="import_staging_status",
        ),
        sa.UniqueConstraint("workspace_id", "batch_id", "entity_type", "source_ref",
                            name="uq_staging_record"),
    )
    op.create_index("ix_staging_batch", "import_staging_record", ["batch_id"])
    op.create_index("ix_staging_entity", "import_staging_record", ["batch_id", "entity_type"])

    _enable_rls("import_batch")
    _enable_rls("import_staging_record")

    # --- permission: import.manage (granted to Super/Workspace Admin) ---
    op.execute(
        "INSERT INTO permission(key, description) "
        "VALUES ('import.manage', 'Stage, review, promote and roll back data imports') "
        "ON CONFLICT (key) DO NOTHING"
    )
    op.execute(
        "INSERT INTO role_permission(role_id, permission_id) "
        "SELECT r.id, p.id FROM role r, permission p "
        "WHERE p.key = 'import.manage' "
        "AND r.workspace_id IS NULL AND r.key IN ('super_admin','workspace_admin') "
        "ON CONFLICT DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permission WHERE permission_id IN "
        "(SELECT id FROM permission WHERE key = 'import.manage')"
    )
    op.execute("DELETE FROM permission WHERE key = 'import.manage'")
    for tbl in ("import_staging_record", "import_batch"):
        op.execute(f"DROP POLICY IF EXISTS {tbl}_workspace_isolation ON {tbl}")
    op.drop_table("import_staging_record")
    op.drop_table("import_batch")
