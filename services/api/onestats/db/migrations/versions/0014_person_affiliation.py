"""Phase 5 Stage 2: person affiliations (roles & participation).

Associates a person with the clubs, teams, associations and competitions they were involved
with over a career — multiple and simultaneous affiliations, transfers, returns to former clubs,
representative participation, and multiple concurrent roles within one organisation. Periods may
be unknown or approximate (``date_approx``). Affiliation is **membership/involvement**, kept
deliberately **distinct from match participation** (a match appearance is established only from
match records, Phase 8) — so club membership never implies someone played a given match.

``role`` is free text (extensible without a schema change) so new roles — Player, Captain,
Vice-Captain, Coach, Assistant Coach, Team Manager, Umpire, Scorer, Club/Association Official,
Life Member, Honorary Member, and any future role — need no migration. Historical research is
supported via ``verification_status``, ``evidence``, ``notes`` and source provenance; unknown
dates stay unknown and participation is never inferred from insufficient evidence.

One workspace-scoped table with FORCE RLS; governed by the existing ``person.manage`` permission.
Rhymney / Moyston / Rhymney-Moyston remain distinct organisations (Phase 4); a person may be
affiliated to each across different periods with attribution preserved — combined career
reporting stays an explicit, approved reporting rule, never an automatic statistic merge.

Revision ID: 0014_person_affiliation
Revises: 0013_people
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014_person_affiliation"
down_revision = "0013_people"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "person_affiliation",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("person.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organisation.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("team.id", ondelete="SET NULL"), nullable=True),
        sa.Column("competition_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("competition.id", ondelete="SET NULL"), nullable=True),
        # Free text = extensible without a migration (standard set documented in the service).
        sa.Column("role", sa.Text(), nullable=False, server_default=sa.text("'player'")),
        sa.Column("valid_from", sa.Date(), nullable=True),   # unknown stays NULL
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("date_approx", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_representative", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("verification_status", sa.Text(), nullable=False, server_default=sa.text("'unverified'")),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "valid_from IS NULL OR valid_to IS NULL OR valid_to >= valid_from",
            name="person_affiliation_dates_ordered"),
        sa.CheckConstraint(
            "verification_status in ('unverified','verified','disputed','corrected')",
            name="person_affiliation_verification"),
    )
    op.create_index("ix_person_affiliation_workspace", "person_affiliation", ["workspace_id"])
    op.create_index("ix_person_affiliation_person", "person_affiliation", ["person_id"])
    op.create_index("ix_person_affiliation_org", "person_affiliation", ["organisation_id"])

    op.execute("ALTER TABLE person_affiliation ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE person_affiliation FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY person_affiliation_workspace_isolation ON person_affiliation "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS person_affiliation_workspace_isolation ON person_affiliation")
    op.drop_table("person_affiliation")
