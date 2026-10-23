"""Phase 5 Stage 1: people & player identity foundation.

Unique, persistent person identities for every cricket participant (players, umpires, scorers,
coaches, administrators, …), with one person able to hold several roles. Historical names,
aliases, initials and incomplete names are preserved with effective dates; external source
identifiers keep provenance and make re-import idempotent. Unknown stays unknown — a date of
birth is optional and carries a precision (Cricket Statz placeholder dates such as 1700-01-01
must be mapped to unknown, never a genuine DOB). A person is never duplicated for representing
different clubs, and same-name/same-initials people are never auto-merged.

Four workspace-scoped tables with FORCE RLS: ``person``, ``person_name_history``,
``person_source_identity``, ``person_role``. Adds the ``person.manage`` permission. Junior
personal data is privacy-protected by default. No identity merges here (Stage 3); ``merged_into_id``
is reserved for that reversible, administrator-approved flow.

Revision ID: 0013_people
Revises: 0012_match_classification_ext
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013_people"
down_revision = "0012_match_classification_ext"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"
_TABLES = ("person", "person_name_history", "person_source_identity", "person_role")


def _ws_fk():
    return sa.Column(
        "workspace_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False,
    )


def _person_fk():
    return sa.Column(
        "person_id", postgresql.UUID(as_uuid=True),
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
        "person",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        _ws_fk(),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("is_junior", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        # Personal data protected by default; always true for juniors (enforced in the service).
        sa.Column("privacy_protected", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("dob", sa.Date(), nullable=True),  # optional; unknown stays NULL
        sa.Column("dob_precision", sa.Text(), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("notes", sa.Text(), nullable=True),
        # Reserved for the Stage 3 reversible, admin-approved merge (no merge logic in Stage 1).
        sa.Column("merged_into_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("person.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "dob_precision in ('unknown','exact','year','month','approx')", name="person_dob_precision"),
    )
    op.create_index("ix_person_workspace", "person", ["workspace_id"])

    op.create_table(
        "person_name_history",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        _ws_fk(), _person_fk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("name_type", sa.Text(), nullable=False, server_default=sa.text("'primary'")),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "name_type in ('primary','alias','initials','maiden','incomplete','other')",
            name="person_name_type"),
    )
    op.create_index("ix_person_name_hist_person", "person_name_history", ["person_id"])

    op.create_table(
        "person_source_identity",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        _ws_fk(), _person_fk(),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("source_display_name", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("workspace_id", "source_system", "source_ref", name="uq_person_source_ref"),
    )
    op.create_index("ix_person_source_person", "person_source_identity", ["person_id"])

    op.create_table(
        "person_role",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        _ws_fk(), _person_fk(),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "role in ('player','umpire','scorer','coach','administrator','selector','captain','other')",
            name="person_role_kind"),
        sa.UniqueConstraint("workspace_id", "person_id", "role", name="uq_person_role"),
    )
    op.create_index("ix_person_role_person", "person_role", ["person_id"])

    for tbl in _TABLES:
        _enable_rls(tbl)

    op.execute(
        "INSERT INTO permission(key, description) "
        "VALUES ('person.manage', 'Manage people, player identities, roles and historical names') "
        "ON CONFLICT (key) DO NOTHING"
    )
    op.execute(
        "INSERT INTO role_permission(role_id, permission_id) "
        "SELECT r.id, p.id FROM role r, permission p "
        "WHERE p.key = 'person.manage' "
        "AND r.workspace_id IS NULL AND r.key IN ('super_admin','workspace_admin') "
        "ON CONFLICT DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permission WHERE permission_id IN "
        "(SELECT id FROM permission WHERE key = 'person.manage')"
    )
    op.execute("DELETE FROM permission WHERE key = 'person.manage'")
    for tbl in reversed(_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {tbl}_workspace_isolation ON {tbl}")
    for tbl in reversed(_TABLES):
        op.drop_table(tbl)
