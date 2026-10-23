"""Phase 5 Stage 4: comprehensive player profiles.

Consolidates personal info, cricket history, player numbers, leadership history, recognition and
photographs **around the existing stable person_id** (Stage 1) — no duplicate identity system. All
affiliations/participation continue to come from Stage 2; this stage adds profile detail and
records that hang off a person. Statistics are NOT stored here (no fabricated totals): career
figures are computed from verified match records in later phases — only reserved integration
contracts exist. Junior/personal data stays privacy-protected, and ``public_visible`` keeps a
profile/photo internal unless explicitly authorised (internal ≠ public).

Five workspace-scoped tables, all FORCE RLS; governed by the existing ``person.manage`` permission.
Life Membership and other recognition stay tied to the awarding organisation and never transfer
automatically on a merger.

Revision ID: 0016_player_profiles
Revises: 0015_person_resolution
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016_player_profiles"
down_revision = "0015_person_resolution"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"
_TABLES = ("person_profile", "person_number", "person_leadership", "person_recognition", "person_photo")


def _ws_fk():
    return sa.Column(
        "workspace_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False,
    )


def _person_fk():
    return sa.Column(
        "person_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("person.id", ondelete="CASCADE"), nullable=False,
    )


def _org_fk(nullable: bool):
    return sa.Column(
        "organisation_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("organisation.id", ondelete="CASCADE"), nullable=nullable,
    )


def _ts(name):
    return sa.Column(name, sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()"))


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_workspace_isolation ON {table} "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def upgrade() -> None:
    # 1:1 profile detail hanging off the person identity.
    op.create_table(
        "person_profile",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        _ws_fk(), _person_fk(),
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column("preferred_display_name", sa.Text(), nullable=True),
        sa.Column("biography", sa.Text(), nullable=True),          # may be public
        sa.Column("research_notes", sa.Text(), nullable=True),     # internal only
        sa.Column("date_of_death", sa.Date(), nullable=True),
        sa.Column("dod_precision", sa.Text(), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("batting_style", sa.Text(), nullable=True),
        sa.Column("bowling_style", sa.Text(), nullable=True),
        sa.Column("is_wicketkeeper", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("career_start", sa.Date(), nullable=True),
        sa.Column("career_end", sa.Date(), nullable=True),
        sa.Column("player_status", sa.Text(), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("verification_status", sa.Text(), nullable=False, server_default=sa.text("'unverified'")),
        sa.Column("public_visible", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        _ts("created_at"), _ts("updated_at"),
        sa.UniqueConstraint("workspace_id", "person_id", name="uq_person_profile"),
        sa.CheckConstraint("player_status in ('current','former','unknown')", name="person_profile_status"),
        sa.CheckConstraint("dod_precision in ('unknown','exact','year','month','approx')", name="person_profile_dod_precision"),
        sa.CheckConstraint(
            "verification_status in ('unverified','supported','verified','disputed','corrected')",
            name="person_profile_verification"),
    )
    op.create_index("ix_person_profile_person", "person_profile", ["person_id"])

    # Player numbers — historical/seasonal, per organisation; never a person identifier.
    op.create_table(
        "person_number",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        _ws_fk(), _person_fk(), _org_fk(nullable=False),
        sa.Column("number", sa.Text(), nullable=True),  # may be unknown
        sa.Column("season_label", sa.Text(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        _ts("created_at"),
    )
    op.create_index("ix_person_number_person", "person_number", ["person_id"])

    # Appointed leadership roles (distinct from match captaincy, which comes from match records).
    op.create_table(
        "person_leadership",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        _ws_fk(), _person_fk(), _org_fk(nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("team.id", ondelete="SET NULL"), nullable=True),
        sa.Column("role", sa.Text(), nullable=False),  # free text, extensible
        sa.Column("season_label", sa.Text(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        _ts("created_at"),
    )
    op.create_index("ix_person_leadership_person", "person_leadership", ["person_id"])

    # Membership & recognition — tied to the awarding organisation (no auto-transfer on merger).
    op.create_table(
        "person_recognition",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        _ws_fk(), _person_fk(), _org_fk(nullable=True),  # representative honours may have no club
        sa.Column("recognition_type", sa.Text(), nullable=False),  # free text, extensible
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("awarded_on", sa.Date(), nullable=True),
        sa.Column("season_label", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        _ts("created_at"),
    )
    op.create_index("ix_person_recognition_person", "person_recognition", ["person_id"])

    # Photographs — metadata; binary stored via the Phase 3 image pipeline (workspace-isolated).
    op.create_table(
        "person_photo",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        _ws_fk(), _person_fk(),
        sa.Column("media_key", sa.Text(), nullable=False),  # stored file reference (non-guessable)
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("approx_date", sa.Text(), nullable=True),
        sa.Column("source_attribution", sa.Text(), nullable=True),
        sa.Column("usage_permissions", sa.Text(), nullable=True),
        sa.Column("public_visible", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("format", sa.Text(), nullable=True),
        _ts("created_at"),
    )
    op.create_index("ix_person_photo_person", "person_photo", ["person_id"])

    for tbl in _TABLES:
        _enable_rls(tbl)


def downgrade() -> None:
    for tbl in reversed(_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {tbl}_workspace_isolation ON {tbl}")
    for tbl in reversed(_TABLES):
        op.drop_table(tbl)
