"""Source Library (Phase 10, Stage 10.1/10.2).

A research source is a historical document (newspaper article/edition, scorebook, photograph, PDF,
website, manual reference, …) with rich citation and copyright metadata. Publication date is stored
and treated separately from the match date. A source links to the canonical match(es) it supports —
it never forces a new match to be created. Duplicate sources are detected by content hash.
Workspace-scoped (FORCE RLS); every change audited.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit

SOURCE_TYPES = (
    "newspaper_article", "newspaper_clipping", "newspaper_edition", "scorebook",
    "handwritten_scorecard", "printed_scorecard", "photograph", "pdf", "image", "club_record",
    "annual_report", "publication", "archived_website", "online_database", "manual_reference",
)
DATE_PRECISION = ("exact", "month", "year", "approximate", "range", "unknown")
OCR_STATUS = ("none", "pending", "done", "failed", "manual")

# Columns a caller may set, besides title/source_type (handled explicitly).
_META = (
    "publication", "author", "publication_date", "publication_date_precision", "edition", "page_ref",
    "original_url", "archive_ref", "source_identifier", "language", "location", "copyright_status",
    "usage_restrictions", "date_accessed", "uploaded_by", "notes", "file_ref", "file_sha256",
    "file_bytes", "content_type", "ocr_status",
)


def find_duplicate_by_hash(conn: Connection, workspace_id: UUID, file_sha256: str) -> dict[str, Any] | None:
    """A source in this workspace with the same file content, if any (duplicate-source detection)."""
    if not file_sha256:
        return None
    r = conn.execute(
        text("SELECT * FROM research_source WHERE workspace_id = :w AND file_sha256 = :h "
             "ORDER BY created_at LIMIT 1"),
        {"w": workspace_id, "h": file_sha256},
    ).mappings().first()
    return dict(r) if r else None


def create_source(conn: Connection, workspace_id: UUID, actor: str, *, title: str, source_type: str,
                  **meta: Any) -> dict[str, Any]:
    if not (title or "").strip():
        raise ValueError("title_required")
    if source_type not in SOURCE_TYPES:
        raise ValueError("invalid_source_type")
    precision = meta.get("publication_date_precision")
    if precision is not None and precision not in DATE_PRECISION:
        raise ValueError("invalid_date_precision")
    ocr = meta.get("ocr_status")
    if ocr is not None and ocr not in OCR_STATUS:
        raise ValueError("invalid_ocr_status")

    cols = ["workspace_id", "title", "source_type"]
    vals = [":w", ":title", ":source_type"]
    params: dict[str, Any] = {"w": workspace_id, "title": title, "source_type": source_type}
    for key in _META:
        if key in meta and meta[key] is not None:
            cols.append(key)
            vals.append(f":{key}")
            params[key] = meta[key]
    sid = conn.execute(
        text(f"INSERT INTO research_source({', '.join(cols)}) VALUES ({', '.join(vals)}) RETURNING id"),
        params,
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "research.source_created", entity="research_source",
                      entity_id=str(sid), after={"title": title, "source_type": source_type})
    return get_source(conn, sid)


def get_source(conn: Connection, source_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text("SELECT * FROM research_source WHERE id = :id"), {"id": source_id}).mappings().first()
    return dict(r) if r else None


def list_sources(conn: Connection, workspace_id: UUID, *, source_type: str | None = None,
                 limit: int | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM research_source WHERE workspace_id = :w"
    params: dict[str, Any] = {"w": workspace_id}
    if source_type is not None:
        sql += " AND source_type = :st"
        params["st"] = source_type
    sql += " ORDER BY created_at DESC"
    if limit is not None:
        sql += " LIMIT :lim"
        params["lim"] = limit
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def link_match(conn: Connection, workspace_id: UUID, actor: str, source_id: UUID, match_id: UUID,
               *, role: str | None = None) -> dict[str, Any]:
    """Attach a source to the canonical match it contributes evidence to (idempotent)."""
    lid = conn.execute(
        text("INSERT INTO research_source_match(workspace_id, source_id, match_id, role, created_by) "
             "VALUES (:w, :s, :m, :r, :by) "
             "ON CONFLICT ON CONSTRAINT uq_research_source_match DO UPDATE SET role = COALESCE(:r, research_source_match.role) "
             "RETURNING id"),
        {"w": workspace_id, "s": source_id, "m": match_id, "r": role, "by": actor},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "research.source_linked", entity="research_source_match",
                      entity_id=str(lid), after={"source_id": str(source_id), "match_id": str(match_id)})
    r = conn.execute(text("SELECT * FROM research_source_match WHERE id = :id"), {"id": lid}).mappings().first()
    return dict(r)


def set_file(conn: Connection, workspace_id: UUID, actor: str, source_id: UUID, *, file_ref: str,
             file_sha256: str, file_bytes: int, content_type: str) -> dict[str, Any]:
    """Record a stored document file on a source and mark it pending OCR/transcription. Returns the
    source plus ``duplicate_of`` (another source in the workspace with identical content), if any —
    detection only; the researcher decides whether it is truly a duplicate."""
    dup = conn.execute(
        text("SELECT id FROM research_source WHERE workspace_id = :w AND file_sha256 = :h AND id <> :id "
             "ORDER BY created_at LIMIT 1"),
        {"w": workspace_id, "h": file_sha256, "id": source_id},
    ).scalar_one_or_none()
    conn.execute(
        text("UPDATE research_source SET file_ref = :fr, file_sha256 = :h, file_bytes = :b, "
             "content_type = :ct, ocr_status = 'pending', updated_at = now() WHERE id = :id"),
        {"fr": file_ref, "h": file_sha256, "b": file_bytes, "ct": content_type, "id": source_id},
    )
    audit.write_audit(conn, workspace_id, actor, "research.source_file_stored", entity="research_source",
                      entity_id=str(source_id), after={"file_sha256": file_sha256, "bytes": file_bytes})
    out = get_source(conn, source_id)
    out["duplicate_of"] = str(dup) if dup is not None else None
    return out


def list_editions(conn: Connection, workspace_id: UUID, publication: str) -> list[dict[str, Any]]:
    """All sources from one publication (its multiple editions/issues), newest publication date first."""
    rows = conn.execute(
        text("SELECT * FROM research_source WHERE workspace_id = :w AND publication = :p "
             "ORDER BY publication_date DESC NULLS LAST, created_at"),
        {"w": workspace_id, "p": publication},
    ).mappings().all()
    return [dict(r) for r in rows]


def list_sources_for_match(conn: Connection, workspace_id: UUID, match_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("SELECT s.*, l.role AS link_role FROM research_source_match l "
             "JOIN research_source s ON s.id = l.source_id "
             "WHERE l.workspace_id = :w AND l.match_id = :m ORDER BY s.publication_date NULLS LAST, s.created_at"),
        {"w": workspace_id, "m": match_id},
    ).mappings().all()
    return [dict(r) for r in rows]
