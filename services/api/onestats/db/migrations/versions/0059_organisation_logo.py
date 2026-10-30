"""Per-organisation (club) logo reference.

Each organisation may carry its own crest/logo so opposing clubs are shown with their own branding,
distinct from the workspace's own club logo. The image bytes live in workspace-isolated media storage
(``domain/logos.py``, under ``<media_root>/branding/<workspace_id>/``); only the generated, non-guessable
filename is stored here. Nullable and additive — existing organisations simply have no logo.

Revision ID: 0059_organisation_logo
Revises: 0058_update_system
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0059_organisation_logo"
down_revision = "0058_update_system"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organisation", sa.Column("logo_ref", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("organisation", "logo_ref")
