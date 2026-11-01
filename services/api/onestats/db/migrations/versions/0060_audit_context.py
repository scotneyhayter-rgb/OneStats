"""Richer audit context for role-based accountability (Part 6).

Adds the actor's role, effective permission, a reason (for sensitive changes), a per-request
id, and a flag recording when the actor was operating as a platform Super Admin inside a
workspace they are not an ordinary member of. All columns are nullable so existing audit
writes keep working unchanged; the row-level-security policy on audit_log is untouched.

Revision ID: 0060_audit_context
Revises: 0059_organisation_logo
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0060_audit_context"
down_revision = "0059_organisation_logo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_log", sa.Column("actor_role", sa.Text(), nullable=True))
    op.add_column("audit_log", sa.Column("effective_permission", sa.Text(), nullable=True))
    op.add_column("audit_log", sa.Column("reason", sa.Text(), nullable=True))
    op.add_column("audit_log", sa.Column("request_id", sa.Text(), nullable=True))
    op.add_column(
        "audit_log",
        sa.Column("acting_as_super_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("audit_log", "acting_as_super_admin")
    op.drop_column("audit_log", "request_id")
    op.drop_column("audit_log", "reason")
    op.drop_column("audit_log", "effective_permission")
    op.drop_column("audit_log", "actor_role")
