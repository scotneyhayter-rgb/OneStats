"""Phase 10, Stage 10.11: historical verification states.

Reconciles the research verification distinctions with the Phase 7 approval state machine rather than
creating a parallel one. Extends ``match.approval_status`` additively with:

* ``verified_partial`` — a reviewer has verified the record as far as it goes; it is known-incomplete
  (its present, verified data is statistics-eligible, exactly as an approved scorecard's present data
  is — the engine only ever aggregates what exists, so nothing is invented to fill gaps).
* ``disputed`` — sources conflict unresolved; the match is held out of official statistics until
  resolved.

The existing draft -> awaiting_approval -> approved / rejected flow is unchanged. Additive (widens a
CHECK only). The match table is already workspace-scoped with FORCE RLS.

Revision ID: 0042_verification_states
Revises: 0041_match_date_range
"""
from __future__ import annotations

from alembic import op

revision = "0042_verification_states"
down_revision = "0041_match_date_range"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("match_approval_status", "match", type_="check")
    op.create_check_constraint(
        "match_approval_status", "match",
        "approval_status in ('draft','awaiting_approval','approved','rejected','verified_partial','disputed')",
    )


def downgrade() -> None:
    # revert any new states to draft before narrowing the constraint, so the CHECK can be re-created
    op.execute("UPDATE match SET approval_status = 'draft' "
               "WHERE approval_status IN ('verified_partial','disputed')")
    op.drop_constraint("match_approval_status", "match", type_="check")
    op.create_check_constraint(
        "match_approval_status", "match",
        "approval_status in ('draft','awaiting_approval','approved','rejected')",
    )
