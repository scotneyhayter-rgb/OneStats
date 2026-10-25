"""Phase 9, Stages 9.4-9.9: discovery coverage + review queue.

* ``discovery_coverage`` — per (workspace, source, scope) record of what has been searched, classified
  as searched / partial / awaiting / no_accessible_source / failed, so the system never claims a
  period was verified merely because a search returned nothing.
* ``discovery_item`` — the review queue: each discovered candidate (a new match, or a proposed change
  to an existing scorecard) with its classification, confidence, source evidence and review status.
  Imported matches still go through the Phase 7 draft/approval workflow — a discovery item is never a
  statistic.

Idempotent discovery: unique on (workspace, source_system, source_ref, kind) so re-discovery updates
in place. Workspace-scoped with FORCE RLS; additive only.

Revision ID: 0037_discovery
Revises: 0036_sync_source
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0037_discovery"
down_revision = "0036_sync_source"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "discovery_coverage",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sync_source.id", ondelete="SET NULL"), nullable=True),
        sa.Column("scope_key", sa.Text(), nullable=False),           # canonical key for the scope
        sa.Column("scope", postgresql.JSONB(), nullable=True),       # competition/season/grade/date range
        sa.Column("status", sa.Text(), nullable=False),              # searched|partial|awaiting|no_source|failed
        sa.Column("matches_found", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("searched_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status in ('searched','partial','awaiting','no_source','failed')",
                           name="discovery_coverage_status"),
        sa.UniqueConstraint("workspace_id", "source_id", "scope_key", name="uq_discovery_coverage"),
    )
    op.create_index("ix_discovery_coverage_ws", "discovery_coverage", ["workspace_id", "status"])

    op.create_table(
        "discovery_item",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sync_source.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),                # new_match | updated_scorecard
        sa.Column("classification", sa.Text(), nullable=False),      # new|existing|possible_duplicate|additional_evidence|conflicting|insufficient
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending_review'")),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("match_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("match.id", ondelete="SET NULL"), nullable=True),
        sa.Column("candidate", postgresql.JSONB(), nullable=True),   # normalised match + evidence/reasons
        sa.Column("proposed_changes", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("kind in ('new_match','updated_scorecard')", name="discovery_item_kind"),
        sa.CheckConstraint(
            "classification in ('new','existing','possible_duplicate','additional_evidence','conflicting','insufficient')",
            name="discovery_item_classification"),
        sa.CheckConstraint("status in ('pending_review','accepted','rejected','auto_imported','superseded')",
                           name="discovery_item_status"),
        sa.UniqueConstraint("workspace_id", "source_system", "source_ref", "kind", name="uq_discovery_item"),
    )
    op.create_index("ix_discovery_item_ws_status", "discovery_item", ["workspace_id", "status"])

    for tbl in ("discovery_coverage", "discovery_item"):
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {tbl}_workspace_isolation ON {tbl} "
                   f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})")


def downgrade() -> None:
    for tbl in ("discovery_item", "discovery_coverage"):
        op.execute(f"DROP POLICY IF EXISTS {tbl}_workspace_isolation ON {tbl}")
        op.drop_table(tbl)
