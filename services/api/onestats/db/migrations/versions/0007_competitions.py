"""Phase 4 Stage 3: competitions, divisions, grades, seasons & entries.

Models the competition structure a club's teams play in, over time and across sources:

* ``competition`` — optionally owned by an association (organisation); operates independently
  when no association is set. Renames are preserved in ``competition_name_history`` and external
  provenance in ``competition_source_identity`` — current arrangements never overwrite history.
* ``division`` — optional grouping within a competition.
* ``grade`` — a graded level within a competition (optionally inside a division). ``program`` is
  free text so administrators can define programs (senior men's/women's, junior boys'/girls',
  mixed junior, all-abilities, …). No team-size limit is imposed here; team-size restrictions are
  configured via Stage 4 playing conditions. Historical grade names live in ``grade_name_history``.
* ``season`` — e.g. "2026/27"; ``start_date``/``end_date`` are nullable (unknown precision), so a
  season may span two calendar years and historical spans back to 1919 are representable.
* ``team_grade_entry`` — team × grade × season: which teams contested which grade when. A team may
  enter different grades in different seasons, several teams from one club may share a grade, and a
  team may appear in more than one competition. ``UNIQUE`` prevents duplicate entries.
* ``match_classification`` — preparatory, unknown-aware controlled vocabulary for finals/home-and-
  away classifications used by later match phases. Unmapped source values are preserved as
  ``status='unresolved'`` (``is_final`` NULL) for later verification — never guessed (D32).

All tables are workspace-scoped with FORCE RLS. Adds the ``competition.manage`` permission.

Revision ID: 0007_competitions
Revises: 0006_venues_teams
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_competitions"
down_revision = "0006_venues_teams"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


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


def _fk(target: str, name: str, ondelete: str = "CASCADE", nullable: bool = False):
    return sa.Column(
        name, postgresql.UUID(as_uuid=True),
        sa.ForeignKey(f"{target}.id", ondelete=ondelete), nullable=nullable,
    )


def _ts(name):
    return sa.Column(name, sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()"))


def _name_hist(parent: str):
    fk_col = f"{parent}_id"
    op.create_table(
        f"{parent}_name_history",
        _pk(), _ws_fk(), _fk(parent, fk_col),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        _ts("created_at"),
    )
    op.create_index(f"ix_{parent}_name_hist_parent", f"{parent}_name_history", [fk_col])


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_workspace_isolation ON {table} "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


_TABLES = (
    "competition", "competition_name_history", "competition_source_identity",
    "division", "grade", "grade_name_history", "season",
    "team_grade_entry", "match_classification",
)


def upgrade() -> None:
    op.create_table(
        "competition",
        _pk(), _ws_fk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("short_name", sa.Text(), nullable=True),
        # Optional association ownership (D31); SET NULL so the competition survives if the org
        # record is removed and operates independently when unset.
        _fk("organisation", "association_id", ondelete="SET NULL", nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        _ts("created_at"),
    )
    op.create_index("ix_competition_workspace", "competition", ["workspace_id"])
    op.create_index("ix_competition_association", "competition", ["association_id"])

    _name_hist("competition")

    op.create_table(
        "competition_source_identity",
        _pk(), _ws_fk(), _fk("competition", "competition_id"),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("source_display_name", sa.Text(), nullable=True),
        _ts("created_at"),
        sa.UniqueConstraint("workspace_id", "source_system", "source_ref",
                            name="uq_competition_source_ref"),
    )
    op.create_index("ix_competition_source_parent", "competition_source_identity", ["competition_id"])

    op.create_table(
        "division",
        _pk(), _ws_fk(), _fk("competition", "competition_id"),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        _ts("created_at"),
    )
    op.create_index("ix_division_competition", "division", ["competition_id"])

    op.create_table(
        "grade",
        _pk(), _ws_fk(), _fk("competition", "competition_id"),
        _fk("division", "division_id", ondelete="SET NULL", nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        # program is free text: administrators may define programs beyond the fixed team enum
        # (e.g. mixed junior, junior boys/girls). No team-size limit here — see Stage 4.
        sa.Column("program", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        _ts("created_at"),
    )
    op.create_index("ix_grade_competition", "grade", ["competition_id"])

    _name_hist("grade")

    op.create_table(
        "season",
        _pk(), _ws_fk(), _fk("competition", "competition_id"),
        sa.Column("label", sa.Text(), nullable=False),  # e.g. "2026/27"
        sa.Column("start_date", sa.Date(), nullable=True),  # nullable = unknown precision
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        _ts("created_at"),
        sa.UniqueConstraint("workspace_id", "competition_id", "label", name="uq_season_label"),
    )
    op.create_index("ix_season_competition", "season", ["competition_id"])

    op.create_table(
        "team_grade_entry",
        _pk(), _ws_fk(),
        _fk("team", "team_id"),
        _fk("grade", "grade_id"),
        _fk("season", "season_id"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        _ts("created_at"),
        sa.UniqueConstraint("workspace_id", "team_id", "grade_id", "season_id",
                            name="uq_team_grade_season"),
    )
    op.create_index("ix_tge_team", "team_grade_entry", ["team_id"])
    op.create_index("ix_tge_grade", "team_grade_entry", ["grade_id"])
    op.create_index("ix_tge_season", "team_grade_entry", ["season_id"])

    op.create_table(
        "match_classification",
        _pk(), _ws_fk(),
        sa.Column("key", sa.Text(), nullable=True),  # e.g. home_away/final/semi_final/... ; NULL when unresolved
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("is_final", sa.Boolean(), nullable=True),  # NULL = unknown (not yet verified)
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'confirmed'")),
        sa.Column("unresolved_source_value", sa.Text(), nullable=True),
        sa.Column("source_system", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        _ts("created_at"),
        sa.CheckConstraint("status in ('confirmed','unresolved')", name="match_classification_status"),
    )
    op.create_index("ix_match_classification_workspace", "match_classification", ["workspace_id"])

    for tbl in _TABLES:
        _enable_rls(tbl)

    # --- permission: competition.manage (granted to Super/Workspace Admin) ---
    op.execute(
        "INSERT INTO permission(key, description) "
        "VALUES ('competition.manage', 'Manage competitions, divisions, grades, seasons and entries') "
        "ON CONFLICT (key) DO NOTHING"
    )
    op.execute(
        "INSERT INTO role_permission(role_id, permission_id) "
        "SELECT r.id, p.id FROM role r, permission p "
        "WHERE p.key = 'competition.manage' "
        "AND r.workspace_id IS NULL AND r.key IN ('super_admin','workspace_admin') "
        "ON CONFLICT DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permission WHERE permission_id IN "
        "(SELECT id FROM permission WHERE key = 'competition.manage')"
    )
    op.execute("DELETE FROM permission WHERE key = 'competition.manage'")
    for tbl in reversed(_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {tbl}_workspace_isolation ON {tbl}")
    for tbl in reversed(_TABLES):
        op.drop_table(tbl)
