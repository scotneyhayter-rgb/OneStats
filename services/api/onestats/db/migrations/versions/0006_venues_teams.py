"""Phase 4 Stage 2: venues & teams.

Grounds (venues) and the teams an organisation fields per program, each workspace-scoped under
FORCE RLS and each carrying the same conservative historical-identity machinery introduced in
Stage 1: period-correct name history, external source identities (provenance), administrator-
approved reversible merges, and explicit "Definitely Different" assertions.

Venues are standalone and reusable by many clubs/teams/competitions; teams are attributable to
an organisation and a cricket program. Adds the separate ``venue.manage`` permission (D34);
teams are governed by the existing ``organisation.manage`` permission. No match data.

Revision ID: 0006_venues_teams
Revises: 0005_organisations
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_venues_teams"
down_revision = "0005_organisations"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"

# parent → the four identity child tables created for it
_IDENTITY_CHILDREN = ("name_history", "source_identity", "merge", "distinct_assertion")


def _pk():
    return sa.Column(
        "id", postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"), primary_key=True,
    )


def _ws_fk():
    return sa.Column(
        "workspace_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False,
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


def _parent_fk(parent: str, name: str, ondelete: str = "CASCADE"):
    return sa.Column(
        name, postgresql.UUID(as_uuid=True),
        sa.ForeignKey(f"{parent}.id", ondelete=ondelete), nullable=False,
    )


def _create_identity_children(parent: str) -> None:
    """Create the four historical-identity tables for ``parent`` (venue or team), mirroring the
    organisation pattern from Stage 1."""
    fk_col = f"{parent}_id"

    op.create_table(
        f"{parent}_name_history",
        _pk(), _ws_fk(), _parent_fk(parent, fk_col),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        _ts("created_at"),
    )
    op.create_index(f"ix_{parent}_name_hist_parent", f"{parent}_name_history", [fk_col])

    op.create_table(
        f"{parent}_source_identity",
        _pk(), _ws_fk(), _parent_fk(parent, fk_col),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("source_display_name", sa.Text(), nullable=True),
        _ts("created_at"),
        sa.UniqueConstraint("workspace_id", "source_system", "source_ref",
                            name=f"uq_{parent}_source_ref"),
    )
    op.create_index(f"ix_{parent}_source_parent", f"{parent}_source_identity", [fk_col])

    op.create_table(
        f"{parent}_merge",
        _pk(), _ws_fk(),
        _parent_fk(parent, f"canonical_{parent}_id"),
        _parent_fk(parent, f"merged_{parent}_id"),
        sa.Column("actor", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        _ts("at"),
        sa.Column("is_undone", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("undone_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("undone_by", sa.Text(), nullable=True),
    )

    op.create_table(
        f"{parent}_distinct_assertion",
        _pk(), _ws_fk(),
        _parent_fk(parent, f"{parent}_a_id"),
        _parent_fk(parent, f"{parent}_b_id"),
        sa.Column("actor", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        _ts("at"),
        sa.CheckConstraint(f"{parent}_a_id <> {parent}_b_id", name=f"{parent}_distinct_differs"),
        sa.UniqueConstraint("workspace_id", f"{parent}_a_id", f"{parent}_b_id",
                            name=f"uq_{parent}_distinct_pair"),
    )

    for child in _IDENTITY_CHILDREN:
        _enable_rls(f"{parent}_{child}")


def upgrade() -> None:
    # --- venue (grounds; standalone, reusable) ---
    op.create_table(
        "venue",
        _pk(), _ws_fk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("short_name", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        # Location/address — all optional; unknown values stay NULL (never invented).
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("locality", sa.Text(), nullable=True),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column("postcode", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("merged_into_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("venue.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        _ts("created_at"),
        sa.CheckConstraint(
            "latitude IS NULL OR (latitude BETWEEN -90 AND 90)", name="venue_latitude_range"
        ),
        sa.CheckConstraint(
            "longitude IS NULL OR (longitude BETWEEN -180 AND 180)", name="venue_longitude_range"
        ),
    )
    op.create_index("ix_venue_workspace", "venue", ["workspace_id"])

    # --- team (an organisation's side in a given program) ---
    op.create_table(
        "team",
        _pk(), _ws_fk(),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organisation.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("short_name", sa.Text(), nullable=True),
        sa.Column("program", sa.Text(), nullable=False, server_default=sa.text("'seniors'")),
        sa.Column("is_historical", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("merged_into_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("team.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        _ts("created_at"),
        sa.CheckConstraint(
            "program in ('seniors','juniors','womens','girls','all_abilities','veterans','custom')",
            name="team_program",
        ),
    )
    op.create_index("ix_team_workspace", "team", ["workspace_id"])
    op.create_index("ix_team_organisation", "team", ["organisation_id"])

    _enable_rls("venue")
    _enable_rls("team")
    _create_identity_children("venue")
    _create_identity_children("team")

    # --- permission: venue.manage (teams reuse the existing organisation.manage) ---
    op.execute(
        "INSERT INTO permission(key, description) "
        "VALUES ('venue.manage', 'Manage venues (grounds) and their historical identities') "
        "ON CONFLICT (key) DO NOTHING"
    )
    op.execute(
        "INSERT INTO role_permission(role_id, permission_id) "
        "SELECT r.id, p.id FROM role r, permission p "
        "WHERE p.key = 'venue.manage' "
        "AND r.workspace_id IS NULL AND r.key IN ('super_admin','workspace_admin') "
        "ON CONFLICT DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permission WHERE permission_id IN "
        "(SELECT id FROM permission WHERE key = 'venue.manage')"
    )
    op.execute("DELETE FROM permission WHERE key = 'venue.manage'")
    for parent in ("team", "venue"):
        for child in reversed(_IDENTITY_CHILDREN):
            tbl = f"{parent}_{child}"
            op.execute(f"DROP POLICY IF EXISTS {tbl}_workspace_isolation ON {tbl}")
        op.execute(f"DROP POLICY IF EXISTS {parent}_workspace_isolation ON {parent}")
    for parent in ("team", "venue"):
        for child in reversed(_IDENTITY_CHILDREN):
            op.drop_table(f"{parent}_{child}")
    op.drop_table("team")
    op.drop_table("venue")
