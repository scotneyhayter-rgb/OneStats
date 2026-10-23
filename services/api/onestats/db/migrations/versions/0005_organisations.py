"""Phase 4 Stage 1: organisations & historical identity.

Clubs / associations / international teams / historical clubs, with period-correct name
history, external source identities (provenance), administrator-approved reversible merges,
and explicit "Definitely Different" assertions. All workspace-scoped with FORCE RLS. Adds
the organisation.manage permission (granted to Super/Workspace Admin). No cricket match data.

Revision ID: 0005_organisations
Revises: 0004_onboarding
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_organisations"
down_revision = "0004_onboarding"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def _pk():
    return sa.Column(
        "id", postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"), primary_key=True,
    )


def _ws_fk(nullable=False):
    return sa.Column(
        "workspace_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=nullable,
    )


def _org_fk(name="organisation_id", ondelete="CASCADE", nullable=False):
    return sa.Column(
        name, postgresql.UUID(as_uuid=True),
        sa.ForeignKey("organisation.id", ondelete=ondelete), nullable=nullable,
    )


def _ts(name):
    return sa.Column(name, sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()"))


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_workspace_isolation ON {table} "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def upgrade() -> None:
    op.create_table(
        "organisation",
        _pk(),
        _ws_fk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("short_name", sa.Text(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False, server_default=sa.text("'club'")),
        sa.Column("is_historical", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("notes", sa.Text(), nullable=True),
        # merged_into_id: when this org has been merged into a canonical one (reversible).
        sa.Column("merged_into_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organisation.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        _ts("created_at"),
        sa.CheckConstraint(
            "kind in ('club','association','intl_team','historical_club')", name="organisation_kind"
        ),
    )
    op.create_index("ix_organisation_workspace", "organisation", ["workspace_id"])

    op.create_table(
        "organisation_name_history",
        _pk(), _ws_fk(), _org_fk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        _ts("created_at"),
    )
    op.create_index("ix_org_name_hist_org", "organisation_name_history", ["organisation_id"])

    op.create_table(
        "organisation_source_identity",
        _pk(), _ws_fk(), _org_fk(),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("source_display_name", sa.Text(), nullable=True),
        _ts("created_at"),
        sa.UniqueConstraint("workspace_id", "source_system", "source_ref", name="uq_org_source_ref"),
    )
    op.create_index("ix_org_source_org", "organisation_source_identity", ["organisation_id"])

    op.create_table(
        "organisation_merge",
        _pk(), _ws_fk(),
        _org_fk("canonical_organisation_id", ondelete="CASCADE"),
        _org_fk("merged_organisation_id", ondelete="CASCADE"),
        sa.Column("actor", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        _ts("at"),
        sa.Column("is_undone", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("undone_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("undone_by", sa.Text(), nullable=True),
    )

    op.create_table(
        "organisation_distinct_assertion",
        _pk(), _ws_fk(),
        _org_fk("organisation_a_id", ondelete="CASCADE"),
        _org_fk("organisation_b_id", ondelete="CASCADE"),
        sa.Column("actor", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        _ts("at"),
        sa.CheckConstraint("organisation_a_id <> organisation_b_id", name="distinct_pair_differs"),
        sa.UniqueConstraint(
            "workspace_id", "organisation_a_id", "organisation_b_id", name="uq_distinct_pair"
        ),
    )

    for tbl in (
        "organisation", "organisation_name_history", "organisation_source_identity",
        "organisation_merge", "organisation_distinct_assertion",
    ):
        _enable_rls(tbl)

    # --- permission: organisation.manage (granted to Super/Workspace Admin) ---
    op.execute(
        "INSERT INTO permission(key, description) "
        "VALUES ('organisation.manage', 'Manage organisations, teams and historical identities') "
        "ON CONFLICT (key) DO NOTHING"
    )
    op.execute(
        "INSERT INTO role_permission(role_id, permission_id) "
        "SELECT r.id, p.id FROM role r, permission p "
        "WHERE p.key = 'organisation.manage' "
        "AND r.workspace_id IS NULL AND r.key IN ('super_admin','workspace_admin') "
        "ON CONFLICT DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permission WHERE permission_id IN "
        "(SELECT id FROM permission WHERE key = 'organisation.manage')"
    )
    op.execute("DELETE FROM permission WHERE key = 'organisation.manage'")
    for tbl in (
        "organisation_distinct_assertion", "organisation_merge",
        "organisation_source_identity", "organisation_name_history", "organisation",
    ):
        op.execute(f"DROP POLICY IF EXISTS {tbl}_workspace_isolation ON {tbl}")
    op.drop_table("organisation_distinct_assertion")
    op.drop_table("organisation_merge")
    op.drop_table("organisation_source_identity")
    op.drop_table("organisation_name_history")
    op.drop_table("organisation")
