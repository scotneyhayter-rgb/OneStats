"""Media backup manifest + integrity verification (Phase 11, Stage 11.8).

A backup of the media archive is the media files (under ``media_root``) plus the database rows. This
module produces a **manifest** — every asset with its stable id, storage locator, checksum and size,
together with its relationships (media_link) and heritage curation — so a backup can be validated and a
restore checked: files can be matched by checksum, missing files detected, and all media relationships
preserved. ``verify_media`` scans the live archive for missing or corrupted internal files.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.core.config import Settings
from onestats.domain.media import assets, migration


def verify_media(conn: Connection, settings: Settings, workspace_id: UUID) -> dict[str, Any]:
    """Scan internal assets for integrity: each must have its file present and its SHA-256 matching.
    External/OneVault assets are reported 'unverifiable' (OneStats cannot read their bytes), never ok."""
    rows = assets.list_assets(conn, workspace_id, limit=100000)
    missing: list[str] = []
    mismatch: list[str] = []
    unverifiable: list[str] = []
    verified = 0
    for a in rows:
        v = migration.verify_asset(settings, workspace_id, a)
        if v["status"] == "ok":
            verified += 1
        elif v["status"] == "missing":
            missing.append(str(a["id"]))
        elif v["status"] == "mismatch":
            mismatch.append(str(a["id"]))
        else:
            unverifiable.append(str(a["id"]))
    return {
        "total": len(rows),
        "verified_ok": verified,
        "missing": missing,
        "mismatch": mismatch,
        "unverifiable": unverifiable,
        "ok": not missing and not mismatch,
    }


def build_manifest(conn: Connection, settings: Settings, workspace_id: UUID) -> dict[str, Any]:
    """A validatable backup descriptor: assets (with checksums + integrity) + relationships + heritage,
    so a restore can confirm every file is present and every relationship is preserved."""
    asset_rows = assets.list_assets(conn, workspace_id, limit=100000)
    manifest_assets = []
    for a in asset_rows:
        v = migration.verify_asset(settings, workspace_id, a)
        manifest_assets.append({
            "id": str(a["id"]),
            "storage_provider": a["storage_provider"],
            "storage_locator": a["storage_locator"],
            "sha256": a["sha256"],
            "file_bytes": a["file_bytes"],
            "content_type": a["content_type"],
            "kind": a["kind"],
            "thumbnail_ref": a["thumbnail_ref"],
            "preview_ref": a["preview_ref"],
            "integrity": v["status"],
        })
    links = [
        {"media_asset_id": str(r["media_asset_id"]), "entity_type": r["entity_type"],
         "entity_id": str(r["entity_id"]), "role": r["role"]}
        for r in conn.execute(
            text("SELECT media_asset_id, entity_type, entity_id, role FROM media_link WHERE workspace_id = :w"),
            {"w": workspace_id}).mappings().all()
    ]
    heritage_rows = [
        {"collection": str(r["collection_id"]), "media_asset_id": str(r["media_asset_id"]) if r["media_asset_id"] else None,
         "significance": r["significance"]}
        for r in conn.execute(
            text("SELECT collection_id, media_asset_id, significance FROM heritage_item WHERE workspace_id = :w"),
            {"w": workspace_id}).mappings().all()
    ]
    integrity = verify_media(conn, settings, workspace_id)
    return {
        "workspace_id": str(workspace_id),
        "asset_count": len(manifest_assets),
        "assets": manifest_assets,
        "links": links,
        "heritage_items": heritage_rows,
        "integrity": integrity,
    }


def check_restore(conn: Connection, settings: Settings, workspace_id: UUID, manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate the live archive against a manifest (e.g. after a restore): which assets in the manifest
    are present with a matching checksum, which are missing, and whether all relationships are present."""
    present, missing_assets, checksum_mismatch = [], [], []
    for ma in manifest.get("assets", []):
        live = assets.get_asset(conn, UUID(ma["id"])) if _is_uuid(ma["id"]) else None
        if live is None:
            missing_assets.append(ma["id"])
            continue
        if ma.get("sha256") and live.get("sha256") and ma["sha256"] != live["sha256"]:
            checksum_mismatch.append(ma["id"])
        else:
            present.append(ma["id"])
    live_links = {
        (str(r["media_asset_id"]), r["entity_type"], str(r["entity_id"]))
        for r in conn.execute(
            text("SELECT media_asset_id, entity_type, entity_id FROM media_link WHERE workspace_id = :w"),
            {"w": workspace_id}).mappings().all()
    }
    missing_links = [
        lk for lk in manifest.get("links", [])
        if (lk["media_asset_id"], lk["entity_type"], lk["entity_id"]) not in live_links
    ]
    return {
        "assets_present": len(present),
        "assets_missing": missing_assets,
        "checksum_mismatch": checksum_mismatch,
        "relationships_missing": missing_links,
        "ok": not missing_assets and not checksum_mismatch and not missing_links,
    }


def _is_uuid(s: str) -> bool:
    try:
        UUID(s)
        return True
    except (ValueError, AttributeError, TypeError):
        return False
