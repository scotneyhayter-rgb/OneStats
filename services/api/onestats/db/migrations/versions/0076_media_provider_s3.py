"""Allow the 's3' media storage provider.

Extends the media_asset provider CHECK constraint to include 's3' (S3-compatible object storage: AWS S3,
Cloudflare R2, MinIO, …) alongside internal / onevault / external, so originals can be migrated to and
served from object storage for cloud / shared-server deployments. No data changes; existing rows keep
their provider.

Revision ID: 0076_media_provider_s3
Revises: 0075_workspace_github_connect
"""
from __future__ import annotations

from alembic import op

revision = "0076_media_provider_s3"
down_revision = "0075_workspace_github_connect"
branch_labels = None
depends_on = None

_OLD = "storage_provider in ('internal','onevault','external')"
_NEW = "storage_provider in ('internal','onevault','external','s3')"


def upgrade() -> None:
    op.drop_constraint("media_asset_provider", "media_asset", type_="check")
    op.create_check_constraint("media_asset_provider", "media_asset", _NEW)


def downgrade() -> None:
    op.drop_constraint("media_asset_provider", "media_asset", type_="check")
    op.create_check_constraint("media_asset_provider", "media_asset", _OLD)
