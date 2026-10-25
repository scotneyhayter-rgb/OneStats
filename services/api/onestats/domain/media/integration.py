"""Phase 10 <-> Phase 11 media integration (Stage 11.9).

Promotes a Phase 10 research source document into a single canonical media asset: the file is MOVED into
the media store (checksum-verified), the research source is pointed at the new asset, and the asset is
linked back to the source. The result is one file and one media record — no duplicate files, duplicate
source records or conflicting media libraries. media depends on research here (research never imports
media), so there is no import cycle.
"""
from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.core.config import Settings
from onestats.domain import audit
from onestats.domain.media import assets
from onestats.domain.research import sources as rsources
from onestats.domain.research import storage as rstorage


def promote_research_source(conn: Connection, settings: Settings, workspace_id: UUID, actor: str,
                            source_id: UUID) -> dict[str, Any]:
    """Create a media_asset from a research source's uploaded document (moving the file into the media
    store). Idempotent: if the source already points at an asset, that asset is returned."""
    src = rsources.get_source(conn, source_id)
    if src is None:
        raise ValueError("source_not_found")
    if src.get("media_asset_id"):
        return assets.get_asset(conn, src["media_asset_id"])
    if not src.get("file_ref"):
        raise ValueError("source_has_no_file")

    path = rstorage.source_file_path(settings, workspace_id, src["file_ref"])
    if path is None:
        raise ValueError("source_file_missing")
    raw = path.read_bytes()
    if src.get("file_sha256") and hashlib.sha256(raw).hexdigest() != src["file_sha256"]:
        raise ValueError("source_integrity_failed")

    asset = assets.create_internal_asset(
        conn, settings, workspace_id, actor, raw=raw,
        content_type=src.get("content_type") or "application/octet-stream",
        original_filename=src.get("title"), kind="document", title=src.get("title"),
        copyright_status=src.get("copyright_status"),
        source_provenance=f"research_source:{source_id}",
    )
    # move: point the research source at the asset and drop its own file copy (original preserved in media)
    conn.execute(
        text("UPDATE research_source SET media_asset_id = :a, file_ref = NULL, updated_at = now() WHERE id = :id"),
        {"a": asset["id"], "id": source_id},
    )
    rstorage.remove_source_file(settings, workspace_id, src["file_ref"])
    assets.link_asset(conn, workspace_id, actor, asset["id"], entity_type="research_source", entity_id=source_id,
                      role="document")
    audit.write_audit(conn, workspace_id, actor, "media.promoted_research_source", entity="media_asset",
                      entity_id=str(asset["id"]), after={"source_id": str(source_id)})
    return assets.get_asset(conn, asset["id"])
