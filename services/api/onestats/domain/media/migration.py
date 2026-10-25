"""Secure storage migration + integrity verification (Phase 11, Stage 11.5).

Move an asset's bytes between storage providers while keeping its **stable media id** (so links never
break), with checksum verification at every step, failure recovery and rollback:

1. Read the source bytes and verify they still match the recorded SHA-256 (corruption pre-check).
2. Write to the target provider and verify the written copy's SHA-256 matches.
3. Only then update the asset's provider/locator; the source copy is kept unless removal is explicitly
   requested, and even then is removed only after the target is verified.

If any step fails the asset is left untouched (original preserved) and the partial target copy is rolled
back. OneStats never deletes an original held in OneVault or an external store.
"""
from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.core.config import Settings
from onestats.domain import audit
from onestats.domain.media import assets, providers


def verify_asset(settings: Settings, workspace_id: UUID, asset: dict[str, Any]) -> dict[str, Any]:
    """Recompute an asset's checksum and compare to the recorded one. External/OneVault assets whose
    bytes OneStats cannot read are reported as 'unverifiable', never silently 'ok'."""
    if asset["storage_provider"] != "internal":
        return {"ok": None, "status": "unverifiable", "reason": f"{asset['storage_provider']} bytes not read by OneStats"}
    if not asset.get("sha256"):
        return {"ok": None, "status": "no_checksum"}
    try:
        raw = assets.asset_bytes(settings, workspace_id, asset)
    except Exception as exc:  # noqa: BLE001 - a missing/unreadable file is a verification failure, reported
        return {"ok": False, "status": "missing", "reason": str(exc)[:200]}
    actual = hashlib.sha256(raw).hexdigest()
    return {"ok": actual == asset["sha256"], "status": "ok" if actual == asset["sha256"] else "mismatch",
            "expected": asset["sha256"], "actual": actual}


def migrate_asset(conn: Connection, settings: Settings, workspace_id: UUID, actor: str, asset_id: UUID, *,
                  to_provider: str, remove_source: bool = False) -> dict[str, Any]:
    asset = assets.get_asset(conn, asset_id)
    if asset is None:
        raise ValueError("asset_not_found")
    if to_provider not in providers.PROVIDERS:
        raise ValueError("unknown_provider")
    if asset["storage_provider"] == "external":
        raise ValueError("cannot_migrate_external")   # OneStats does not own these bytes
    if to_provider == "external":
        raise ValueError("cannot_migrate_to_external")  # external is register-only, not a byte target

    src = providers.get_provider(asset["storage_provider"])
    # 1. read source + integrity pre-check (never migrate corrupted bytes)
    raw = src.get(settings, workspace_id, asset["storage_locator"])
    if asset.get("sha256") and hashlib.sha256(raw).hexdigest() != asset["sha256"]:
        audit.write_audit(conn, workspace_id, actor, "media.migration_aborted", entity="media_asset",
                          entity_id=str(asset_id), after={"reason": "source_integrity_failed"})
        raise ValueError("source_integrity_failed")

    # 2. write to target (may raise ProviderUnavailable for OneVault without a verified API -> no change)
    target = providers.get_provider(to_provider)
    stored = target.put(settings, workspace_id, raw, asset.get("content_type") or "application/octet-stream")

    # 3. verify the written copy, else roll back
    if asset.get("sha256") and str(stored["sha256"]) != asset["sha256"]:
        target.delete(settings, workspace_id, str(stored["locator"]))
        audit.write_audit(conn, workspace_id, actor, "media.migration_rolled_back", entity="media_asset",
                          entity_id=str(asset_id), after={"reason": "target_verify_failed"})
        raise ValueError("migration_verify_failed")

    old_provider, old_locator = asset["storage_provider"], asset["storage_locator"]
    conn.execute(
        text("UPDATE media_asset SET storage_provider = :p, storage_locator = :loc, updated_at = now() "
             "WHERE id = :id"),
        {"p": to_provider, "loc": str(stored["locator"]), "id": asset_id},
    )
    removed = False
    if remove_source and not (old_provider == to_provider and old_locator == str(stored["locator"])):
        providers.get_provider(old_provider).delete(settings, workspace_id, old_locator)
        removed = True
    audit.write_audit(conn, workspace_id, actor, "media.migrated", entity="media_asset", entity_id=str(asset_id),
                      after={"from": old_provider, "to": to_provider, "verified": True, "source_removed": removed})
    out = assets.get_asset(conn, asset_id)
    out["migration"] = {"from": old_provider, "to": to_provider, "verified": True, "source_removed": removed}
    return out
