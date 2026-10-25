"""Phase 13, Stage 13.8: Life Members & honorary recognition.

Explicitly recorded, authorised honours — Life Members, Honorary Members, club awards and historical
figures. These are NEVER inferred from match counts or years of service; they are entered and confirmed
by authorised administrators, with supporting evidence and an optional linked photograph (Phase 11
media). Distinct from automatically-calculated statistical achievements (badges).

Workspace-scoped (FORCE RLS); additive only. Adds ``honour.manage`` (granted to Super/Workspace Admin).

Revision ID: 0048_honours
Revises: 0047_research_source_media
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0048_honours"
down_revision = "0047_research_source_media"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "honour",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("person.id", ondelete="SET NULL"), nullable=True),
        sa.Column("honour_type", sa.Text(), nullable=False),  # life_member|honorary_member|club_award|historical_figure|other
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("awarded_date", sa.Date(), nullable=True),
        sa.Column("awarded_season", sa.Text(), nullable=True),
        sa.Column("awarding_organisation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organisation.id", ondelete="SET NULL"), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("media_asset_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("media_asset.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'confirmed'")),  # proposed|confirmed
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "honour_type in ('life_member','honorary_member','club_award','historical_figure','other')",
            name="honour_type"),
        sa.CheckConstraint("status in ('proposed','confirmed')", name="honour_status"),
    )
    op.create_index("ix_honour_ws", "honour", ["workspace_id", "honour_type"])
    op.create_index("ix_honour_person", "honour", ["person_id"])

    op.execute("ALTER TABLE honour ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE honour FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY honour_workspace_isolation ON honour "
               f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})")

    op.execute("INSERT INTO permission(key, description) VALUES "
               "('honour.manage', 'Record and confirm Life Members, honorary members and club awards') "
               "ON CONFLICT (key) DO NOTHING")
    op.execute("INSERT INTO role_permission(role_id, permission_id) "
               "SELECT r.id, p.id FROM role r, permission p WHERE p.key = 'honour.manage' "
               "AND r.workspace_id IS NULL AND r.key IN ('super_admin','workspace_admin') ON CONFLICT DO NOTHING")


def downgrade() -> None:
    op.execute("DELETE FROM role_permission WHERE permission_id IN (SELECT id FROM permission WHERE key = 'honour.manage')")
    op.execute("DELETE FROM permission WHERE key = 'honour.manage'")
    op.execute("DROP POLICY IF EXISTS honour_workspace_isolation ON honour")
    op.drop_table("honour")
