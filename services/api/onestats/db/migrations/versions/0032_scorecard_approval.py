"""Phase 7 Stage 7.1: scorecard approval workflow (separate from match status).

Additive only. Adds an approval workflow to ``match`` that is INDEPENDENT of the match's cricket
status (draft/final/abandoned):

* ``approval_status`` — ``draft`` → ``awaiting_approval`` → ``approved`` / ``rejected``. Only an
  ``approved`` scorecard is the authoritative source for official statistical calculations (enforced
  by the recalculation framework in Stage 7.8). Defaults to ``draft``.
* ``approval_reason`` — note/reason recorded on a transition (e.g. why rejected).
* ``approved_by`` / ``approved_at`` — who approved it and when (set on approval, cleared otherwise).

Also adds the ``scorecard.approve`` permission (granted to super_admin and workspace_admin), so
approving/rejecting is an administrator action distinct from editing a draft.

Revision ID: 0032_scorecard_approval
Revises: 0031_match_formats
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0032_scorecard_approval"
down_revision = "0031_match_formats"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("match", sa.Column("approval_status", sa.Text(), nullable=False,
                                     server_default=sa.text("'draft'")))
    op.add_column("match", sa.Column("approval_reason", sa.Text(), nullable=True))
    op.add_column("match", sa.Column("approved_by", postgresql.UUID(as_uuid=True),
                                     sa.ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True))
    op.add_column("match", sa.Column("approved_at", sa.TIMESTAMP(timezone=True), nullable=True))
    # true when an approved scorecard has been edited since approval — official statistics keep using
    # the last approved version (Stage 7.8 ledger) until the revision is re-approved.
    op.add_column("match", sa.Column("revised_since_approval", sa.Boolean(), nullable=False,
                                     server_default=sa.text("false")))
    op.create_check_constraint(
        "match_approval_status", "match",
        "approval_status in ('draft','awaiting_approval','approved','rejected')")
    op.create_index("ix_match_approval_status", "match", ["approval_status"])

    op.execute("INSERT INTO permission(key, description) "
               "VALUES ('scorecard.approve', 'Approve or reject scorecards for official statistics') "
               "ON CONFLICT (key) DO NOTHING")
    op.execute(
        "INSERT INTO role_permission(role_id, permission_id) "
        "SELECT r.id, p.id FROM role r, permission p "
        "WHERE p.key = 'scorecard.approve' "
        "AND r.workspace_id IS NULL AND r.key IN ('super_admin','workspace_admin') "
        "ON CONFLICT DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM role_permission WHERE permission_id IN (SELECT id FROM permission WHERE key = 'scorecard.approve')")
    op.execute("DELETE FROM permission WHERE key = 'scorecard.approve'")
    op.drop_index("ix_match_approval_status", table_name="match")
    op.drop_constraint("match_approval_status", "match", type_="check")
    op.drop_column("match", "revised_since_approval")
    op.drop_column("match", "approved_at")
    op.drop_column("match", "approved_by")
    op.drop_column("match", "approval_reason")
    op.drop_column("match", "approval_status")
