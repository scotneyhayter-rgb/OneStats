"""Mobile upload — QR-paired, short-lived, scoped upload sessions (deliverable 20a).

A desktop user with media-upload permission starts a pairing session; the phone uses the single-use/short-
lived **token** (only its SHA-256 hash is stored) to upload media over the LAN. Sessions are time-limited,
revocable and workspace-isolated (FORCE RLS). No long-lived credential ever lands on the phone, and the
token is never stored or logged in plaintext.

Revision ID: 0056_upload_session
Revises: 0055_workspace_credential
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0056_upload_session"
down_revision = "0055_workspace_credential"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "upload_session",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),          # SHA-256 of the pairing token (never the token)
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("scope", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),  # optional target
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("upload_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('active','revoked','closed')", name="upload_session_status"),
    )
    op.create_index("ix_upload_session_ws", "upload_session", ["workspace_id", "status"])
    op.create_index("ix_upload_session_token", "upload_session", ["token_hash"])

    op.execute("ALTER TABLE upload_session ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE upload_session FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY upload_session_workspace_isolation ON upload_session "
               f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS upload_session_workspace_isolation ON upload_session")
    op.drop_table("upload_session")
