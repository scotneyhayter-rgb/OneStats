"""Phase 4 Stage 5: organisation lifecycle & historical relationships.

Models how organisations evolve over time as **time-bounded relationships between distinct
organisations** — mergers/amalgamations, renames, affiliations, association transfers, and
predecessor/successor links — without ever merging their underlying identities or reassigning
their historical records. (Identity de-duplication remains the separate Stage 1 merge.)

``organisation_relationship``:

* ``from_org_id`` → ``to_org_id`` (distinct orgs; ``CHECK`` forbids self-links).
* ``rel_type`` = merger | amalgamation | rename | affiliation | association_transfer |
  predecessor | successor | other.
* ``valid_from`` / ``valid_to`` — nullable (unknown dates stay explicitly unresolved); a
  ``CHECK`` keeps a known range ordered.
* ``evidence`` + ``source_system`` / ``source_ref`` — supporting evidence and provenance.
* ``is_void`` / ``voided_at`` / ``voided_by`` — relationships are reversible and correctable; a
  void preserves the original row rather than deleting it.

Workspace-scoped with FORCE RLS; governed by the existing ``organisation.manage`` permission.

Revision ID: 0009_org_relationships
Revises: 0008_playing_conditions
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009_org_relationships"
down_revision = "0008_playing_conditions"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "organisation_relationship",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organisation.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organisation.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rel_type", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),   # nullable = unknown
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("is_void", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("voided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("voided_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("from_org_id <> to_org_id", name="org_rel_distinct"),
        sa.CheckConstraint(
            "rel_type in ('merger','amalgamation','rename','affiliation',"
            "'association_transfer','predecessor','successor','other')",
            name="org_rel_type",
        ),
        sa.CheckConstraint(
            "valid_from IS NULL OR valid_to IS NULL OR valid_to >= valid_from",
            name="org_rel_dates_ordered",
        ),
    )
    op.create_index("ix_org_rel_workspace", "organisation_relationship", ["workspace_id"])
    op.create_index("ix_org_rel_from", "organisation_relationship", ["from_org_id"])
    op.create_index("ix_org_rel_to", "organisation_relationship", ["to_org_id"])

    op.execute("ALTER TABLE organisation_relationship ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE organisation_relationship FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY organisation_relationship_workspace_isolation ON organisation_relationship "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS organisation_relationship_workspace_isolation "
        "ON organisation_relationship"
    )
    op.drop_table("organisation_relationship")
