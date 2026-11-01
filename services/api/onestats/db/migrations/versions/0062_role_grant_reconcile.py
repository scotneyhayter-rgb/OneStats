"""Reconcile built-in role grants with the permissions endpoints actually enforce (Part 1).

The permission catalogue evolved (e.g. the scorecard workflow is gated by ``match.manage`` and
``scorecard.approve``; people by ``person.manage``; research by ``research.manage`` /
``research.verify``) but several built-in roles were still seeded only with the older keys
(``scorecard.draft``, ``record.verify``, ``people.manage``, ``research.run`` …). As a result the
Scorecard Editor could not enter/submit scorecards and the Data Verifier could not approve them.

This migration is **purely additive** — it only grants the missing permissions each of the six
canonical roles needs for its primary workflow, so the roles become genuinely functional. It
removes no grants and touches no user data. Idempotent (ON CONFLICT DO NOTHING).

Revision ID: 0062_role_grant_reconcile
Revises: 0061_match_submitted_by
"""
from __future__ import annotations

from alembic import op

revision = "0062_role_grant_reconcile"
down_revision = "0061_match_submitted_by"
branch_labels = None
depends_on = None

# role key -> permissions to ADD (only ones the role was missing for its real workflow)
_ADDITIONS: dict[str, list[str]] = {
    # Scorecard Editor: create/edit/submit scorecards + enter batting/bowling/innings (match.manage)
    "scorecard_entry": ["match.manage"],
    # Researcher: run the Research Centre (research.manage) + investigate player identity (person.manage)
    "researcher": ["research.manage", "person.manage"],
    # Data Verifier: approve/return scorecards (scorecard.approve + match.manage to reopen), verify
    # research (research.manage/verify), and check identities/duplicates (person.manage)
    "reviewer": ["scorecard.approve", "match.manage", "research.manage", "research.verify", "person.manage"],
    # Legacy People Manager: the people endpoints are gated by person.manage
    "people_manager": ["person.manage"],
}


def _pairs() -> list[tuple[str, str]]:
    return [(rk, pk) for rk, perms in _ADDITIONS.items() for pk in perms]


def upgrade() -> None:
    for role_key, perm_key in _pairs():
        op.execute(
            "INSERT INTO role_permission(role_id, permission_id) "
            "SELECT r.id, p.id FROM role r, permission p "
            f"WHERE r.key = '{role_key}' AND r.workspace_id IS NULL AND p.key = '{perm_key}' "
            "ON CONFLICT DO NOTHING"
        )


def downgrade() -> None:
    for role_key, perm_key in _pairs():
        op.execute(
            "DELETE FROM role_permission rp USING role r, permission p "
            f"WHERE rp.role_id = r.id AND rp.permission_id = p.id "
            f"AND r.key = '{role_key}' AND r.workspace_id IS NULL AND p.key = '{perm_key}'"
        )
