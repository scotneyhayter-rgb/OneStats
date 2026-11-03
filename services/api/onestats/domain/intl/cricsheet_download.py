"""Cricsheet download + import orchestrator (Parts F/G).

Cricsheet publishes men's internationals as per-format ZIP bundles of per-match JSON files. This module
runs the end-to-end pipeline:

    fetch the bundle (SSRF-hardened, allow-list enforced) -> iterate its match JSONs -> parse (the
    cricket-accurate parser) -> import (idempotent, identity-safe) -> record an honest import-log row.

Guarantees and honesty:
  * Only the agreed allow-list is fetched (``intl.sources.is_fetchable``); the fetch itself goes through
    the research engine's SSRF-hardened ``Fetcher`` (host validation, redirect re-validation, size cap).
  * The downloaded bytes are DATA: the ZIP is opened with the standard library, each entry size-capped,
    and only ``*.json`` entries are read; nothing is executed.
  * De-dup + revised-file detection: each match's file checksum is logged. A re-run of an UNCHANGED file
    (same checksum, already imported) is skipped; a changed checksum re-imports (the importer updates in
    place, never duplicates). An approved/verified match is preserved (importer returns skipped_verified).
  * Every match yields an honest log row: ``awaiting_verification`` (imported, not yet approved),
    ``skipped`` (unchanged/duplicate/verified-kept) or ``failed`` (with the reason). Nothing is approved
    automatically — imported matches await human verification.
  * Batch friendly: ``max_items`` bounds a run so a large bundle is processed in controlled batches
    (used by the resumable backfill).
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections.abc import Iterator
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit
from onestats.domain.intl import cricsheet, sources
from onestats.domain.intl import cricsheet_import as importer

# Cricsheet per-format men's international bundles.
BUNDLES = {"test": "tests", "odi": "odis", "t20i": "t20is"}
DEFAULT_BASE_URL = "https://cricsheet.org/downloads/"
# A format bundle is tens of MB; allow well beyond the per-page default, and accept zip content types.
BUNDLE_MAX_BYTES = 200_000_000
_ZIP_CONTENT_TYPES = ("application/zip", "application/octet-stream", "application/x-zip-compressed")
_MAX_ENTRY_BYTES = 5_000_000           # a single match JSON is small; cap each entry defensively


def bundle_url(fmt: str, *, base_url: str = DEFAULT_BASE_URL) -> str:
    if fmt not in BUNDLES:
        raise ValueError("invalid_format")
    return f"{base_url.rstrip('/')}/{BUNDLES[fmt]}_json.zip"


def make_fetcher(**kwargs: Any):
    """A Fetcher configured for Cricsheet bundles (zip content types, larger cap). Injectable transport
    for offline tests via ``transport=``."""
    from onestats.domain.research.webfetch import ALLOWED_CONTENT_TYPES, Fetcher
    return Fetcher(allowed_content_types=ALLOWED_CONTENT_TYPES + _ZIP_CONTENT_TYPES,
                   max_bytes=BUNDLE_MAX_BYTES, **kwargs)


def fetch_bundle(fmt: str, *, fetcher: Any, base_url: str = DEFAULT_BASE_URL):
    """Fetch one format bundle, refusing any host not on the agreed allow-list BEFORE the request."""
    url = bundle_url(fmt, base_url=base_url)
    host = url.split("://", 1)[-1].split("/", 1)[0]
    if not sources.is_fetchable(host):
        raise ValueError(f"host_not_allowed:{host}")
    return fetcher.fetch(url)


def iter_bundle(raw: bytes, *, only_refs: set[str] | None = None) -> Iterator[tuple[str, bytes, dict[str, Any]]]:
    """Yield ``(source_ref, file_bytes, doc)`` for each ``*.json`` match file in a Cricsheet zip. The
    source_ref is the filename stem (the Cricsheet match id). README/txt entries are ignored."""
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        for info in zf.infolist():
            name = info.filename
            if not name.lower().endswith(".json") or info.is_dir():
                continue
            ref = name.rsplit("/", 1)[-1][:-5]       # strip path + ".json"
            if only_refs is not None and ref not in only_refs:
                continue
            if info.file_size > _MAX_ENTRY_BYTES:
                yield ref, b"", {"__too_large__": True}
                continue
            with zf.open(info) as fh:
                data = fh.read(_MAX_ENTRY_BYTES + 1)
            try:
                doc = json.loads(data)
            except (ValueError, UnicodeDecodeError):
                doc = {"__invalid_json__": True}
            yield ref, data, doc


def _log(conn: Connection, workspace_id: UUID, actor: str, source_ref: str, *, status: str,
         fmt: str | None = None, detail: str | None = None, match_id: Any = None,
         sha: str | None = None, source_url: str | None = None) -> None:
    url = source_url
    conn.execute(
        text("INSERT INTO cricsheet_import_log(workspace_id, source_ref, format, status, detail, "
             "match_id, content_sha256, source_url, imported_by) "
             "VALUES (:w, :sr, :f, :st, :d, :m, :sha, :url, :by) "
             "ON CONFLICT ON CONSTRAINT uq_cricsheet_import_log_ref DO UPDATE SET "
             "format = EXCLUDED.format, status = EXCLUDED.status, detail = EXCLUDED.detail, "
             "match_id = EXCLUDED.match_id, content_sha256 = EXCLUDED.content_sha256, "
             "source_url = EXCLUDED.source_url, imported_by = EXCLUDED.imported_by, updated_at = now()"),
        {"w": workspace_id, "sr": source_ref, "f": fmt, "st": status, "d": detail, "m": match_id,
         "sha": sha, "url": url, "by": actor},
    )


def _prior(conn: Connection, workspace_id: UUID, source_ref: str) -> dict[str, Any] | None:
    r = conn.execute(
        text("SELECT status, content_sha256 FROM cricsheet_import_log "
             "WHERE workspace_id = :w AND source_ref = :sr"),
        {"w": workspace_id, "sr": source_ref},
    ).mappings().first()
    return dict(r) if r else None


def import_one(conn: Connection, workspace_id: UUID, actor: str, source_ref: str, file_bytes: bytes,
               doc: dict[str, Any], *, source_url: str | None = None) -> str:
    """Parse + import one match document and record an honest log row. Returns the outcome status
    (``awaiting_verification`` | ``skipped`` | ``failed``)."""
    if doc.get("__too_large__") or doc.get("__invalid_json__"):
        _log(conn, workspace_id, actor, source_ref, status="failed", source_url=source_url,
             detail="oversized or invalid JSON entry — not imported")
        return "failed"
    sha = hashlib.sha256(file_bytes).hexdigest() if file_bytes else None
    prior = _prior(conn, workspace_id, source_ref)
    if prior and prior["status"] == "awaiting_verification" and sha and prior["content_sha256"] == sha:
        _log(conn, workspace_id, actor, source_ref, status="skipped", match_id=None, sha=sha,
             source_url=source_url, detail="unchanged source file (same checksum) — already imported")
        return "skipped"
    try:
        parsed = cricsheet.parse_match(doc, source_ref=source_ref)
    except ValueError as exc:
        _log(conn, workspace_id, actor, source_ref, status="failed", source_url=source_url,
             sha=sha, detail=str(exc))
        return "failed"
    try:
        result = importer.import_match(conn, workspace_id, actor, parsed)
    except Exception as exc:  # noqa: BLE001 - any import error is recorded, never crashes the batch
        _log(conn, workspace_id, actor, source_ref, status="failed", fmt=parsed.format,
             source_url=source_url, sha=sha, detail=f"import error: {exc}")
        return "failed"
    if result["status"] == "skipped_verified":
        _log(conn, workspace_id, actor, source_ref, status="skipped", fmt=parsed.format,
             match_id=result["match_id"], sha=sha, source_url=source_url,
             detail="an approved/verified scorecard is preserved; not overwritten")
        return "skipped"
    _log(conn, workspace_id, actor, source_ref, status="awaiting_verification", fmt=parsed.format,
         match_id=result["match_id"], sha=sha, source_url=source_url,
         detail=f"imported ({result['status']}); awaiting verification")
    return "awaiting_verification"


def import_matches(conn: Connection, workspace_id: UUID, actor: str,
                   items: Iterator[tuple[str, bytes, dict[str, Any]]], *,
                   max_items: int | None = None, source_url: str | None = None) -> dict[str, Any]:
    """Process an iterator of ``(source_ref, file_bytes, doc)`` (e.g. from :func:`iter_bundle`), bounded
    by ``max_items`` for batching. Returns genuine counts and the refs processed (for checkpointing)."""
    counts = {"imported": 0, "skipped": 0, "failed": 0}
    processed: list[str] = []
    for source_ref, file_bytes, doc in items:
        outcome = import_one(conn, workspace_id, actor, source_ref, file_bytes, doc, source_url=source_url)
        counts["imported" if outcome == "awaiting_verification" else outcome] += 1
        processed.append(source_ref)
        if max_items is not None and len(processed) >= max_items:
            break
    audit.write_audit(conn, workspace_id, actor, "cricsheet.import_batch", entity="workspace",
                      entity_id=str(workspace_id), after={"processed": len(processed), **counts})
    return {"processed": len(processed), "last_ref": processed[-1] if processed else None,
            "awaiting_verification": counts["imported"], "skipped": counts["skipped"],
            "failed": counts["failed"], "refs": processed}


def summary(conn: Connection, workspace_id: UUID) -> dict[str, Any]:
    """Counts by status for the Import Management dashboard — genuine, from the log."""
    rows = conn.execute(
        text("SELECT status, count(*) AS n FROM cricsheet_import_log WHERE workspace_id = :w GROUP BY status"),
        {"w": workspace_id},
    ).mappings().all()
    by = {r["status"]: r["n"] for r in rows}
    return {"awaiting_verification": by.get("awaiting_verification", 0),
            "skipped": by.get("skipped", 0), "failed": by.get("failed", 0),
            "total": sum(by.values())}
