"""Add workspace.public_base_url so each club can configure where its published site is hosted.

Publishing is hosting-neutral: a club can download the static files and upload them to any host (e.g.
GitHub Pages). Once they know the public web address their site lives at, storing it here lets OneStats
show the real, copyable public URL for each published report/profile and link them from the portal.
It is a display/address value only — the public edge still serves cached snapshots and never exposes the
database. NULL means "not hosted yet" (the pre-existing behaviour: download-and-upload).

Revision ID: 0073_workspace_public_base_url
Revises: 0072_match_officials
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0073_workspace_public_base_url"
down_revision = "0072_match_officials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workspace", sa.Column("public_base_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("workspace", "public_base_url")
