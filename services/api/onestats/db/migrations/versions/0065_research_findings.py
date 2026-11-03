"""Internet Research Engine, Stage 2: findings + fetch provenance.

* ``research_finding`` — the review queue for one job: each candidate the engine extracted from a web
  page (a possible match, scorecard, result, player detail, report or newspaper item) with its
  classification, an OPTIONAL confidence (NULL = unknown, never 0), the structured extraction (which
  asserts nothing — any value may be null/unknown), a verbatim excerpt for provenance, the source URL
  and content hash. A finding is NEVER a statistic: it is reviewed and only then flows through the
  existing Phase 7 approval workflow. Nothing is auto-approved.

* ``research_fetch`` — honest provenance of what was actually retrieved: every URL the engine touched,
  with the outcome (fetched / blocked / failed / disallowed / too_large / wrong_type / duplicate), HTTP
  status, byte size and content hash. An empty or blocked fetch is recorded as such, so "examined,
  nothing found" is never confused with "could not access" (mirrors Phase 9 discovery-coverage honesty).

Idempotency: findings unique on (workspace, job, url); fetches unique on (workspace, job, url).
Workspace-scoped with FORCE RLS; additive only.

Revision ID: 0065_research_findings
Revises: 0064_research_jobs
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0065_research_findings"
down_revision = "0064_research_jobs"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "research_finding",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("research_job.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("source_host", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),               # match_candidate|scorecard|result|player_info|report|newspaper|other
        sa.Column("classification", sa.Text(), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending_review'")),
        sa.Column("confidence", sa.Float(), nullable=True),         # NULL = unknown (NOT zero)
        sa.Column("summary", sa.Text(), nullable=True),             # short human-readable description
        sa.Column("extracted", postgresql.JSONB(), nullable=True),  # structured candidate; asserts nothing
        sa.Column("raw_excerpt", sa.Text(), nullable=True),         # verbatim snippet (provenance; untrusted data)
        sa.Column("content_sha256", sa.Text(), nullable=True),
        sa.Column("retrieved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("match_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("match.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("research_source.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "kind in ('match_candidate','scorecard','result','player_info','report','newspaper','other')",
            name="research_finding_kind"),
        sa.CheckConstraint(
            "classification in ('new','possible_duplicate','additional_evidence','conflicting','insufficient','unknown')",
            name="research_finding_classification"),
        sa.CheckConstraint(
            "status in ('pending_review','accepted','rejected','linked','superseded')",
            name="research_finding_status"),
        sa.CheckConstraint("confidence is null or (confidence >= 0 and confidence <= 1)",
                           name="research_finding_confidence_range"),
        sa.UniqueConstraint("workspace_id", "job_id", "url", name="uq_research_finding"),
    )
    op.create_index("ix_research_finding_ws_status", "research_finding", ["workspace_id", "status"])
    op.create_index("ix_research_finding_job", "research_finding", ["job_id"])

    op.create_table(
        "research_fetch",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("research_job.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),            # fetched|blocked|failed|disallowed|too_large|wrong_type|duplicate
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.Text(), nullable=True),
        sa.Column("bytes", sa.Integer(), nullable=True),
        sa.Column("content_sha256", sa.Text(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),              # why blocked/failed (no secrets)
        sa.Column("retrieved_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "outcome in ('fetched','blocked','failed','disallowed','too_large','wrong_type','duplicate')",
            name="research_fetch_outcome"),
        sa.UniqueConstraint("workspace_id", "job_id", "url", name="uq_research_fetch"),
    )
    op.create_index("ix_research_fetch_job", "research_fetch", ["job_id"])

    for tbl in ("research_finding", "research_fetch"):
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {tbl}_workspace_isolation ON {tbl} "
                   f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})")


def downgrade() -> None:
    for tbl in ("research_fetch", "research_finding"):
        op.execute(f"DROP POLICY IF EXISTS {tbl}_workspace_isolation ON {tbl}")
        op.drop_table(tbl)
