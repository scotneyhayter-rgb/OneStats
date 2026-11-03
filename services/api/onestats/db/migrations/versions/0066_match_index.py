"""International match-index register (International Men's Cricket, Part C).

An authoritative register of international matches *expected to exist*, independent of whether a
scorecard has yet been imported. Each row is one match with a STABLE internal OneStats identity
(``id``) plus the external ids by which authoritative sources refer to it (``source_refs`` JSONB:
``{"espncricinfo": "63001", "wikipedia": "...", ...}``), so repeated discovery/import reconciles to
the same row and never duplicates.

The register tracks five DISTINCT progress states — these are deliberately separate so the system
never conflates "we expect this match" with "we have its scorecard" with "we have verified it":

    expected   — reconciled from >= 2 authoritative sources to exist; no detail indexed yet
    indexed    — external refs + provisional metadata recorded; scorecard not yet imported
    imported   — a scorecard has been imported (draft/pending) and linked via ``match_id``
    complete   — the imported scorecard is structurally complete (all innings present)
    verified   — approved/verified against the sources (the approval workflow)

Official recognition matters: not every national-team fixture has international status. Status is an
explicit field — ``recognised`` matches progress through the states above; ``candidate`` (status
unclear) and ``disputed`` are held as RESEARCH items and are NEVER auto-imported; ``not_international``
is recorded so a known non-international fixture is not rediscovered as a candidate forever.

Honesty: ``expected`` counts live in ``match_index_coverage`` and are set ONLY by reconciling multiple
sources — never hardcoded, never fabricated. An unknown count stays NULL (distinct from zero), and an
unsearched scope stays ``unknown`` (distinct from "searched, none found"), mirroring
``discovery_coverage``.

Workspace-scoped with FORCE RLS; additive only.

Revision ID: 0066_match_index
Revises: 0065_research_findings
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0066_match_index"
down_revision = "0065_research_findings"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_workspace_isolation ON {table} "
        f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})"
    )


def upgrade() -> None:
    op.create_table(
        "match_index_entry",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        # the imported match, once one exists; SET NULL if the match is later deleted (the index
        # row survives so the match is not silently dropped from the expected register).
        sa.Column("match_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("match.id", ondelete="SET NULL"), nullable=True),
        sa.Column("format", sa.Text(), nullable=False),            # 'test' | 'odi' | 't20i'
        sa.Column("state", sa.Text(), nullable=False, server_default=sa.text("'expected'")),
        sa.Column("official_status", sa.Text(), nullable=False, server_default=sa.text("'recognised'")),
        # provisional identity (from the index sources) — never asserted as verified fact
        sa.Column("match_number", sa.Integer(), nullable=True),    # e.g. Test #2345 (NULL = unknown)
        sa.Column("start_date", sa.Date(), nullable=True),         # unknown stays NULL
        sa.Column("date_precision", sa.Text(), nullable=False, server_default=sa.text("'exact'")),
        sa.Column("team_a", sa.Text(), nullable=True),             # provisional label, resolved to team identities later
        sa.Column("team_b", sa.Text(), nullable=True),
        sa.Column("venue_name", sa.Text(), nullable=True),
        sa.Column("series", sa.Text(), nullable=True),
        # external source references, keyed by source system -> that source's id for this match
        sa.Column("source_refs", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        # which sources have been reconciled for THIS match and whether they agree it exists
        sa.Column("source_agreement", postgresql.JSONB(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),        # NULL = unknown (NOT zero)
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_reconciled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("imported_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("format in ('test','odi','t20i')", name="match_index_format"),
        sa.CheckConstraint(
            "state in ('expected','indexed','imported','complete','verified')",
            name="match_index_state"),
        sa.CheckConstraint(
            "official_status in ('recognised','candidate','disputed','not_international')",
            name="match_index_official_status"),
        sa.CheckConstraint(
            "date_precision in ('unknown','exact','year','month','approx')",
            name="match_index_date_precision"),
        sa.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
                           name="match_index_confidence_range"),
        # at most one index row per imported match
        sa.UniqueConstraint("workspace_id", "match_id", name="uq_match_index_match"),
    )
    op.create_index("ix_match_index_ws_format_state", "match_index_entry",
                    ["workspace_id", "format", "state"])
    op.create_index("ix_match_index_ws_status", "match_index_entry",
                    ["workspace_id", "official_status"])
    op.create_index("ix_match_index_date", "match_index_entry", ["workspace_id", "start_date"])
    # fast lookup / dedupe by a source's external id (GIN over the refs object)
    op.create_index("ix_match_index_source_refs", "match_index_entry", ["source_refs"],
                    postgresql_using="gin")
    _enable_rls("match_index_entry")

    # --- per-scope coverage honesty (format x period): expected counts set ONLY by reconciliation ---
    op.create_table(
        "match_index_coverage",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("format", sa.Text(), nullable=False),
        sa.Column("period", sa.Text(), nullable=False),            # e.g. a year '1877' or 'all'
        sa.Column("coverage_state", sa.Text(), nullable=False, server_default=sa.text("'unknown'")),
        # expected_count is NULL until reconciliation establishes it — unknown is NOT zero.
        sa.Column("expected_count", sa.Integer(), nullable=True),
        sa.Column("indexed_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("imported_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("verified_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        # which sources were consulted for this scope and what each claimed (provenance of the count)
        sa.Column("sources", postgresql.JSONB(), nullable=True),
        sa.Column("last_reconciled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("format in ('test','odi','t20i')", name="match_index_coverage_format"),
        sa.CheckConstraint(
            "coverage_state in ('unknown','searching','partial','reconciled','failed')",
            name="match_index_coverage_state"),
        sa.CheckConstraint("expected_count IS NULL OR expected_count >= 0",
                           name="match_index_coverage_expected_nonneg"),
        sa.UniqueConstraint("workspace_id", "format", "period", name="uq_match_index_coverage"),
    )
    op.create_index("ix_match_index_coverage_ws", "match_index_coverage", ["workspace_id", "format"])
    _enable_rls("match_index_coverage")


def downgrade() -> None:
    for tbl in ("match_index_coverage", "match_index_entry"):
        op.execute(f"DROP POLICY IF EXISTS {tbl}_workspace_isolation ON {tbl}")
        op.drop_table(tbl)
