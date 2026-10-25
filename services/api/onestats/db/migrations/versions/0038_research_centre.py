"""Phase 10, Stage 10.1: Research Centre foundation (spine schema).

The Historical Research Centre reconstructs matches from multiple historical sources while keeping
**one canonical match record** (reusing Phase 6 scorecards, Phase 7 approval, Phase 8 ``match_source``
and Phase 9 discovery). This migration adds the research spine:

* ``research_project`` — a scoped line of research (club/competition/season/date range + aliases) with
  an owner, status and notes; drives discovery and groups sources/matches/tasks.
* ``research_source`` — the Source Library: a historical document (newspaper article/edition, scorebook,
  photograph, PDF, website, manual reference, …) with rich citation + copyright metadata. **Publication
  date is stored separately from match date** and carries an explicit precision/uncertainty. Holds a
  storage reference + integrity hash + OCR status (file bytes live in the storage abstraction, not here).
* ``research_source_match`` — links a source to the canonical match(es) it contributes evidence to
  (many-to-many); a source is never required to create a new match row.
* ``research_note`` — research notebook entries (findings/questions/hypotheses) with an evidence class
  (verified/supported/oral_history/unverified/disputed), distinct from formal scorecard approval.
* ``research_task`` — a research gap turned into a prioritised work item.

All tables are workspace-scoped with FORCE RLS; additive only. Adds ``research.manage`` and
``research.verify`` permissions (granted to Super/Workspace Admin).

Revision ID: 0038_research_centre
Revises: 0037_discovery
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0038_research_centre"
down_revision = "0037_discovery"
branch_labels = None
depends_on = None

_WS = "NULLIF(current_setting('onestats.workspace_id', true), '')::uuid"
_TABLES = ("research_task", "research_note", "research_source_match", "research_source", "research_project")


def _rls(tbl: str) -> None:
    op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {tbl}_workspace_isolation ON {tbl} "
               f"USING (workspace_id = {_WS}) WITH CHECK (workspace_id = {_WS})")


def upgrade() -> None:
    # --- research_project ---------------------------------------------------------------
    op.create_table(
        "research_project",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("scope", postgresql.JSONB(), nullable=True),   # club/competition/season/date-range/aliases
        sa.Column("owner", sa.Text(), nullable=True),            # assigned researcher (user id/label)
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status in ('active','paused','completed','archived')", name="research_project_status"),
    )
    op.create_index("ix_research_project_ws", "research_project", ["workspace_id", "status"])

    # --- research_source (Source Library) -----------------------------------------------
    op.create_table(
        "research_source",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("publication", sa.Text(), nullable=True),      # newspaper / organisation / publisher
        sa.Column("author", sa.Text(), nullable=True),
        # Publication date is NOT the match date; both the value and its certainty are preserved.
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("publication_date_precision", sa.Text(), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("edition", sa.Text(), nullable=True),
        sa.Column("page_ref", sa.Text(), nullable=True),
        sa.Column("original_url", sa.Text(), nullable=True),
        sa.Column("archive_ref", sa.Text(), nullable=True),      # archive / collection reference
        sa.Column("source_identifier", sa.Text(), nullable=True),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),         # geographic location
        sa.Column("copyright_status", sa.Text(), nullable=True),
        sa.Column("usage_restrictions", sa.Text(), nullable=True),
        sa.Column("date_accessed", sa.Date(), nullable=True),
        sa.Column("uploaded_by", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        # storage abstraction (OneVault-ready, deliverable 20/21): a reference, hash + size, not bytes.
        sa.Column("file_ref", sa.Text(), nullable=True),
        sa.Column("file_sha256", sa.Text(), nullable=True),
        sa.Column("file_bytes", sa.BigInteger(), nullable=True),
        sa.Column("content_type", sa.Text(), nullable=True),
        sa.Column("ocr_status", sa.Text(), nullable=False, server_default=sa.text("'none'")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "source_type in ('newspaper_article','newspaper_clipping','newspaper_edition','scorebook',"
            "'handwritten_scorecard','printed_scorecard','photograph','pdf','image','club_record',"
            "'annual_report','publication','archived_website','online_database','manual_reference')",
            name="research_source_type"),
        sa.CheckConstraint(
            "publication_date_precision in ('exact','month','year','approximate','range','unknown')",
            name="research_source_pubdate_precision"),
        sa.CheckConstraint("ocr_status in ('none','pending','done','failed','manual')",
                           name="research_source_ocr_status"),
    )
    op.create_index("ix_research_source_ws", "research_source", ["workspace_id", "source_type"])
    # Duplicate-source detection: the same file content in a workspace is flagged by hash.
    op.create_index("ix_research_source_sha", "research_source", ["workspace_id", "file_sha256"])

    # --- research_source_match (source → canonical match link) --------------------------
    op.create_table(
        "research_source_match",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("research_source.id", ondelete="CASCADE"), nullable=False),
        sa.Column("match_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("match.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.Text(), nullable=True),            # e.g. primary / supporting / corroborating
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("source_id", "match_id", name="uq_research_source_match"),
    )
    op.create_index("ix_research_source_match_match", "research_source_match", ["match_id"])

    # --- research_note ------------------------------------------------------------------
    op.create_table(
        "research_note",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("research_project.id", ondelete="CASCADE"), nullable=True),
        sa.Column("match_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("match.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("research_source.id", ondelete="SET NULL"), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("evidence_class", sa.Text(), nullable=False, server_default=sa.text("'unverified'")),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "evidence_class in ('verified','supported','oral_history','unverified','disputed')",
            name="research_note_evidence_class"),
    )
    op.create_index("ix_research_note_ws", "research_note", ["workspace_id"])
    op.create_index("ix_research_note_project", "research_note", ["project_id"])

    # --- research_task ------------------------------------------------------------------
    op.create_table(
        "research_task",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("research_project.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("gap_kind", sa.Text(), nullable=True),        # missing_scorecard / unknown_result / ...
        sa.Column("scope", postgresql.JSONB(), nullable=True),  # season/grade/team/date range the task targets
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'open'")),
        sa.Column("assigned_to", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint("status in ('open','in_progress','resolved','dismissed')", name="research_task_status"),
    )
    op.create_index("ix_research_task_ws", "research_task", ["workspace_id", "status", "priority"])

    for tbl in _TABLES:
        _rls(tbl)

    # --- permissions --------------------------------------------------------------------
    op.execute(
        "INSERT INTO permission(key, description) VALUES "
        "('research.manage', 'Create research projects, sources, notes and reconstruct historical scorecards'),"
        "('research.verify', 'Review and verify historical research findings') "
        "ON CONFLICT (key) DO NOTHING"
    )
    op.execute(
        "INSERT INTO role_permission(role_id, permission_id) "
        "SELECT r.id, p.id FROM role r, permission p "
        "WHERE p.key IN ('research.manage','research.verify') "
        "AND r.workspace_id IS NULL AND r.key IN ('super_admin','workspace_admin') "
        "ON CONFLICT DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permission WHERE permission_id IN "
        "(SELECT id FROM permission WHERE key IN ('research.manage','research.verify'))"
    )
    op.execute("DELETE FROM permission WHERE key IN ('research.manage','research.verify')")
    for tbl in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS {tbl}_workspace_isolation ON {tbl}")
        op.drop_table(tbl)
