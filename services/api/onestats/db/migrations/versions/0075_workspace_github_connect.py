"""Store a per-workspace GitHub connection for one-click 'Publish to web'.

Lets a club push its published static site straight to a GitHub Pages repository instead of exporting a
zip and uploading by hand. Three nullable columns on ``workspace``:

* ``github_repo``   — the target repository as ``owner/name`` (e.g. ``scotneyhayter-rgb/rmcc-stats``).
* ``github_branch`` — the branch GitHub Pages serves from (defaults to ``main`` when unset).
* ``github_token``  — a fine-grained personal access token with Contents write on that one repo. It is
  stored server-side only and is **never returned to the client** (write-only); the public edge never
  reads it. Only approved, public snapshots are ever pushed — the database is never exposed.

NULLs mean "not connected" (the pre-existing export-and-upload behaviour is unchanged).

Revision ID: 0075_workspace_github_connect
Revises: 0074_hat_tricks_unassigned_wkts
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0075_workspace_github_connect"
down_revision = "0074_hat_tricks_unassigned_wkts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workspace", sa.Column("github_repo", sa.Text(), nullable=True))
    op.add_column("workspace", sa.Column("github_branch", sa.Text(), nullable=True))
    op.add_column("workspace", sa.Column("github_token", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("workspace", "github_token")
    op.drop_column("workspace", "github_branch")
    op.drop_column("workspace", "github_repo")
