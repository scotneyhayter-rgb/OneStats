"""Workspace API & Integrations — per-workspace encrypted provider credentials.

Each workspace (club/association) stores its own external-provider credentials. The **secret** (API key/
token) is encrypted at rest (``secret_enc``, Fernet) with a key kept **outside** the database; non-secret
configuration (org id, tenant, base URL, options) lives in ``config``. FORCE RLS isolates every row to its
workspace, so one club can never read or use another's credentials. Credential lifecycle (create/rotate/
revoke/test/enable) is audited in the workspace ``audit_log``.

Revision ID: 0055_workspace_credential
Revises: 0054_admin_audit
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0055_workspace_credential"
down_revision = "0054_admin_audit"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "workspace_credential",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("secret_enc", sa.Text(), nullable=True),          # Fernet ciphertext of the secret fields
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),  # non-secret
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("rotated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_test_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_test_ok", sa.Boolean(), nullable=True),
        sa.Column("last_test_message", sa.Text(), nullable=True),   # never contains secrets
        sa.Column("last_success_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('active','revoked')", name="workspace_credential_status"),
        sa.UniqueConstraint("workspace_id", "provider", "label", name="uq_workspace_credential"),
    )
    op.create_index("ix_workspace_credential_ws", "workspace_credential", ["workspace_id", "provider"])

    op.execute("ALTER TABLE workspace_credential ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workspace_credential FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY workspace_credential_workspace_isolation ON workspace_credential "
               f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS workspace_credential_workspace_isolation ON workspace_credential")
    op.drop_table("workspace_credential")
