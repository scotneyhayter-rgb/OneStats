"""Phase 3: workspace branding, RBAC (roles/permissions/memberships), FORCE RLS.

Adds the workspace-isolation + role-based-access foundation (deliverables 6, 7, 9).
Workspace-scoped tables get RLS **with FORCE** (so even the owner is policy-bound, D2a);
the runtime connects as the non-owner onestats_app, which is always RLS-bound. The
policies key off the per-transaction GUC `onestats.workspace_id` (set via SET LOCAL by the
data-access layer). Built-in roles/permissions are seeded as global reference data.

No cricket-domain tables and no authentication tables here (auth is a later stage).

Revision ID: 0002_workspaces_rbac
Revises: 0001_foundation
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_workspaces_rbac"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None

# Workspace-scoped isolation predicate (fail-closed: no GUC -> no rows).
_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        primary_key=True,
    )


def upgrade() -> None:
    # --- Existing audit_log: enforce RLS for owners too (D2a) ---
    op.execute("ALTER TABLE audit_log FORCE ROW LEVEL SECURITY")

    # --- branding (one row per workspace) ---
    op.create_table(
        "branding",
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("primary_colour", sa.Text(), nullable=True),
        sa.Column("secondary_colour", sa.Text(), nullable=True),
        sa.Column("third_colour", sa.Text(), nullable=True),
        sa.Column("fourth_colour", sa.Text(), nullable=True),
        sa.Column("accent_colour", sa.Text(), nullable=True),
        sa.Column("theme_mode", sa.Text(), nullable=False, server_default=sa.text("'system'")),
        sa.Column("background", postgresql.JSONB(), nullable=True),
        sa.Column("logo_ref", sa.Text(), nullable=True),
        sa.Column("alt_logos", postgresql.JSONB(), nullable=True),
        sa.Column("tagline", sa.Text(), nullable=True),
        sa.Column("presets", postgresql.JSONB(), nullable=True),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )

    # --- permission (global reference) ---
    op.create_table(
        "permission",
        _uuid_pk(),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.UniqueConstraint("key", name="uq_permission_key"),
    )

    # --- role (built-in = global/workspace_id NULL; custom = workspace-scoped) ---
    op.create_table(
        "role",
        _uuid_pk(),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "uq_role_builtin_key", "role", ["key"], unique=True,
        postgresql_where=sa.text("workspace_id IS NULL"),
    )
    op.create_index(
        "uq_role_custom_key", "role", ["workspace_id", "key"], unique=True,
        postgresql_where=sa.text("workspace_id IS NOT NULL"),
    )

    # --- role_permission ---
    op.create_table(
        "role_permission",
        sa.Column(
            "role_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("role.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column(
            "permission_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("permission.id", ondelete="CASCADE"), primary_key=True,
        ),
    )

    # --- app_user_workspace_role (membership: user x workspace x role) ---
    op.create_table(
        "app_user_workspace_role",
        _uuid_pk(),
        sa.Column(
            "app_user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "workspace_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "role_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("role.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.UniqueConstraint(
            "app_user_id", "workspace_id", "role_id", name="uq_membership"
        ),
    )
    op.create_index(
        "ix_membership_workspace", "app_user_workspace_role", ["workspace_id"]
    )

    # Seed built-in reference data BEFORE enabling (FORCE) RLS on `role`, so the
    # built-in rows (workspace_id IS NULL) are not rejected by the policy's WITH CHECK.
    _seed_rbac()

    # --- RLS (FORCE) on workspace-scoped tables ---
    for tbl in ("branding", "app_user_workspace_role"):
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {tbl}_workspace_isolation ON {tbl} "
            f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
        )
    # role: built-in (NULL workspace) always visible; custom only in-workspace.
    # WITH CHECK forbids creating global roles at runtime (only workspace-scoped).
    op.execute("ALTER TABLE role ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE role FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY role_visibility ON role "
        f"USING (workspace_id IS NULL OR workspace_id = {_WS}) "
        f"WITH CHECK (workspace_id = {_WS})"
    )


def _seed_rbac() -> None:
    permissions = {
        "workspace.onboard": "Create and onboard a workspace",
        "workspace.manage": "Manage workspace settings",
        "branding.manage": "Change branding/theme",
        "user.admin": "User administration",
        "match.view": "View matches and statistics",
        "scorecard.draft": "Enter/edit draft scorecards",
        "record.verify": "Edit verified records / change verification state",
        "people.manage": "Manage people and profiles",
        "identity.merge.propose": "Propose an identity merge",
        "identity.merge.approve": "Approve/execute an identity merge",
        "identity.distinct.mark": "Mark records as Definitely Different",
        "identity.undo_merge": "Undo a merge / split a player",
        "conflict.resolve": "Resolve same-match identity conflicts",
        "research.run": "Run/record research",
        "research.approve": "Approve research verification",
        "import.configure": "Configure import connectors",
        "import.run": "Run imports to staging",
        "import.approve": "Approve imports into canonical records",
        "media.manage": "Manage media assets",
        "publish.configure": "Configure website publishing",
        "publish.approve": "Approve publish / withdraw",
        "protected.view": "View protected junior/DOB data",
        "export": "Export reports (PDF/Excel)",
        "ask.query": "Ask OneStats (deterministic queries)",
    }
    roles = {
        "super_admin": "Super Administrator",
        "workspace_admin": "Workspace Administrator",
        "researcher": "Researcher",
        "scorecard_entry": "Scorecard Entry",
        "people_manager": "People Manager",
        "reviewer": "Reviewer",
        "viewer": "Viewer",
    }
    # Role -> permission keys (deliverable 7). super_admin gets all.
    grants: dict[str, set[str]] = {
        "super_admin": set(permissions),
        "workspace_admin": set(permissions) - {"workspace.onboard"},
        "researcher": {
            "match.view", "scorecard.draft", "people.manage",
            "identity.merge.propose", "identity.distinct.mark",
            "research.run", "import.run", "media.manage", "export", "ask.query",
        },
        "scorecard_entry": {
            "match.view", "scorecard.draft", "import.run", "export", "ask.query",
        },
        "people_manager": {
            "match.view", "people.manage", "identity.merge.propose",
            "identity.distinct.mark", "protected.view", "export", "ask.query",
        },
        "reviewer": {
            "match.view", "scorecard.draft", "record.verify",
            "identity.merge.propose", "identity.merge.approve",
            "identity.distinct.mark", "identity.undo_merge", "conflict.resolve",
            "research.run", "research.approve", "import.run", "import.approve",
            "media.manage", "publish.approve", "export", "ask.query",
        },
        "viewer": {"match.view", "ask.query", "export"},
    }

    perm_id = {k: str(uuid.uuid4()) for k in permissions}
    role_id = {k: str(uuid.uuid4()) for k in roles}

    perm_tbl = sa.table(
        "permission", sa.column("id"), sa.column("key"), sa.column("description")
    )
    role_tbl = sa.table(
        "role", sa.column("id"), sa.column("key"), sa.column("name"),
        sa.column("is_builtin"), sa.column("workspace_id"),
    )
    rp_tbl = sa.table(
        "role_permission", sa.column("role_id"), sa.column("permission_id")
    )

    op.bulk_insert(
        perm_tbl,
        [{"id": perm_id[k], "key": k, "description": v} for k, v in permissions.items()],
    )
    op.bulk_insert(
        role_tbl,
        [
            {"id": role_id[k], "key": k, "name": v, "is_builtin": True, "workspace_id": None}
            for k, v in roles.items()
        ],
    )
    op.bulk_insert(
        rp_tbl,
        [
            {"role_id": role_id[rk], "permission_id": perm_id[pk]}
            for rk, pks in grants.items()
            for pk in pks
        ],
    )


def downgrade() -> None:
    for tbl in ("branding", "app_user_workspace_role", "role"):
        op.execute(f"DROP POLICY IF EXISTS {tbl}_workspace_isolation ON {tbl}")
    op.execute("DROP POLICY IF EXISTS role_visibility ON role")
    op.drop_table("role_permission")
    op.drop_index("ix_membership_workspace", table_name="app_user_workspace_role")
    op.drop_table("app_user_workspace_role")
    op.drop_table("branding")
    op.drop_index("uq_role_custom_key", table_name="role")
    op.drop_index("uq_role_builtin_key", table_name="role")
    op.drop_table("role")
    op.drop_table("permission")
    op.execute("ALTER TABLE audit_log NO FORCE ROW LEVEL SECURITY")
