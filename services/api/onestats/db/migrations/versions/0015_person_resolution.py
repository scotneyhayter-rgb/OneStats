"""Phase 5 Stage 3: person identity resolution — duplicate detection & merging.

Evidence-based person de-duplication that protects historical statistics. Reuses
``person.merged_into_id`` (reserved in Stage 1) for reversible, administrator-approved merges and
adds three workspace-scoped tables (all FORCE RLS):

* ``person_merge`` — append-only, reversible merge log (canonical ← merged), with reason/evidence
  and undo metadata. A merge never deletes the merged record or its evidence.
* ``person_distinct_assertion`` — "definitely different" pairs (e.g. two different A Bonner); once
  recorded, the pair is never re-suggested and can never be merged.
* ``person_duplicate_review`` — the review queue backing a future Identity Resolution Centre:
  pending suggestions with evidence/confidence, resolved to merged / distinct / deferred /
  rejected, every decision audited. Supports competing identity possibilities (J Smith …) without
  ever auto-merging.

Governed by the existing ``person.manage`` permission. No data reset; additive only.

Revision ID: 0015_person_resolution
Revises: 0014_person_affiliation
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015_person_resolution"
down_revision = "0014_person_affiliation"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"
_TABLES = ("person_merge", "person_distinct_assertion", "person_duplicate_review")


def _ws_fk():
    return sa.Column(
        "workspace_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False,
    )


def _person_fk(name: str):
    return sa.Column(
        name, postgresql.UUID(as_uuid=True),
        sa.ForeignKey("person.id", ondelete="CASCADE"), nullable=False,
    )


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_workspace_isolation ON {table} "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def upgrade() -> None:
    op.create_table(
        "person_merge",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        _ws_fk(),
        _person_fk("canonical_person_id"),
        _person_fk("merged_person_id"),
        sa.Column("actor", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("is_undone", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("undone_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("undone_by", sa.Text(), nullable=True),
        sa.CheckConstraint("canonical_person_id <> merged_person_id", name="person_merge_distinct"),
    )
    op.create_index("ix_person_merge_workspace", "person_merge", ["workspace_id"])
    op.create_index("ix_person_merge_merged", "person_merge", ["merged_person_id"])

    op.create_table(
        "person_distinct_assertion",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        _ws_fk(),
        _person_fk("person_a_id"),
        _person_fk("person_b_id"),
        sa.Column("actor", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("person_a_id <> person_b_id", name="person_distinct_differs"),
        sa.UniqueConstraint("workspace_id", "person_a_id", "person_b_id", name="uq_person_distinct_pair"),
    )

    op.create_table(
        "person_duplicate_review",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        _ws_fk(),
        _person_fk("person_a_id"),
        _person_fk("person_b_id"),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("confidence", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("person_a_id <> person_b_id", name="person_review_differs"),
        sa.CheckConstraint(
            "status in ('pending','merged','distinct','deferred','rejected')",
            name="person_review_status"),
    )
    op.create_index("ix_person_review_workspace", "person_duplicate_review", ["workspace_id"])
    op.create_index("ix_person_review_status", "person_duplicate_review", ["status"])

    for tbl in _TABLES:
        _enable_rls(tbl)


def downgrade() -> None:
    for tbl in reversed(_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {tbl}_workspace_isolation ON {tbl}")
    for tbl in reversed(_TABLES):
        op.drop_table(tbl)
