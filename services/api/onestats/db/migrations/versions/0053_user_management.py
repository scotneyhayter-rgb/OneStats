"""Super-Admin user management & secure first-login (post-Phase-17 security work).

Adds the columns/tables needed for administered user accounts: temporary single-use passwords with a
required first-login change, time-limited invitations, and login-attempt records (rate limiting + login
history). These are **global** platform tables (like ``app_user``/``session``) — not workspace-scoped —
managed by the Super Administrator; they never store plaintext passwords (only Argon2id hashes and hashed
tokens).

Revision ID: 0053_user_management
Revises: 0052_publication
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0053_user_management"
down_revision = "0052_publication"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # require a password change on first login (temporary passwords), with an expiry for the temp password
    op.add_column("app_user", sa.Column("must_change_password", sa.Boolean(), nullable=False,
                                        server_default=sa.text("false")))
    op.add_column("app_user", sa.Column("password_expires_at", sa.TIMESTAMP(timezone=True), nullable=True))

    # time-limited, single-use invitations: an invited account is activated by setting a password via token
    op.create_table(
        "user_invitation",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("app_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("token_hash", name="uq_user_invitation_token"),
    )
    op.create_index("ix_user_invitation_user", "user_invitation", ["app_user_id"])

    # login attempts: rate limiting + login history (no secrets stored)
    op.create_table(
        "login_attempt",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("app_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_login_attempt_username_at", "login_attempt", ["username", "at"])


def downgrade() -> None:
    op.drop_table("login_attempt")
    op.drop_table("user_invitation")
    op.drop_column("app_user", "password_expires_at")
    op.drop_column("app_user", "must_change_password")
