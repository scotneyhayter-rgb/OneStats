"""Capture who submitted a scorecard for approval (separation of duties, Part 1 role 5).

Records the user who moved a scorecard to 'awaiting_approval' so the verification workflow can
tell whether the approver is the same person who submitted it. A single column on `match`;
nullable (historical/already-approved rows have no recorded submitter). No stats are affected.

Revision ID: 0061_match_submitted_by
Revises: 0060_audit_context
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0061_match_submitted_by"
down_revision = "0060_audit_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("match", sa.Column("submitted_by", sa.Text(), nullable=True))
    op.add_column("match", sa.Column("submitted_at", sa.TIMESTAMP(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("match", "submitted_at")
    op.drop_column("match", "submitted_by")
