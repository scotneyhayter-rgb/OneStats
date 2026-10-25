"""Media assets (Phase 11, Stages 11.1/11.2/11.9).

Create, read and organise media assets across the storage providers, keyed by the stable media id.
Originals are preserved at original quality; thumbnails and previews are generated **separately** (the
original is never modified in place). Internal access to an asset never implies permission to publish it
— publication eligibility is an explicit, separate control. Assets link to any entity (match, person,
research source, …) via media_link.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.core.config import Settings
from onestats.domain import audit
from onestats.domain.media import providers

_META_COLS = (
    "kind", "title", "description", "caption", "copyright_status", "licence", "attribution",
    "source_provenance", "visibility", "publication_eligible", "sensitive", "junior_protected",
)
LINK_ENTITY_TYPES = ("match", "person", "research_source", "season", "organisation", "team", "other")


def _derivatives(settings: Settings, workspace_id: UUID, raw: bytes, content_type: str) -> dict[str, str | None]:
    """Generate a thumbnail + preview for images, stored as separate files. Never touches the original.
    Returns {} refs when derivatives cannot be made (e.g. a PDF) — honest, not a fake image."""
    out: dict[str, str | None] = {"thumbnail_ref": None, "preview_ref": None}
    if not (content_type or "").lower().startswith("image/"):
        return out
    try:
        from onestats.core import images
        internal = providers.internal_provider()
        thumb = images.make_thumbnail(raw, (256, 256))
        preview = images.make_thumbnail(raw, (1200, 1200))
        out["thumbnail_ref"] = str(internal.put(settings, workspace_id, thumb, "image/png")["locator"])
        out["preview_ref"] = str(internal.put(settings, workspace_id, preview, "image/png")["locator"])
    except Exception:  # noqa: BLE001 - a derivative failure must never block preserving the original
        out = {"thumbnail_ref": None, "preview_ref": None}
    return out


def find_duplicate(conn: Connection, workspace_id: UUID, sha256: str) -> UUID | None:
    if not sha256:
        return None
    return conn.execute(
        text("SELECT id FROM media_asset WHERE workspace_id = :w AND sha256 = :h ORDER BY created_at LIMIT 1"),
        {"w": workspace_id, "h": sha256},
    ).scalar_one_or_none()


def create_internal_asset(conn: Connection, settings: Settings, workspace_id: UUID, actor: str, *,
                          raw: bytes, content_type: str, original_filename: str | None = None,
                          **meta: Any) -> dict[str, Any]:
    """Store an uploaded original on the internal provider (preserved unaltered) + derive thumbnail/
    preview, then record the media_asset. Reports ``duplicate_of`` when identical content already exists."""
    internal = providers.internal_provider()
    stored = internal.put(settings, workspace_id, raw, content_type)
    dup = find_duplicate(conn, workspace_id, str(stored["sha256"]))
    deriv = _derivatives(settings, workspace_id, raw, content_type)
    aid = _insert(conn, workspace_id, actor, storage_provider="internal", storage_locator=str(stored["locator"]),
                  original_filename=original_filename, content_type=content_type,
                  file_bytes=int(stored["bytes"]), sha256=str(stored["sha256"]),
                  thumbnail_ref=deriv["thumbnail_ref"], preview_ref=deriv["preview_ref"], **meta)
    audit.write_audit(conn, workspace_id, actor, "media.asset_created", entity="media_asset",
                      entity_id=str(aid), after={"provider": "internal", "bytes": stored["bytes"]})
    out = get_asset(conn, aid)
    out["duplicate_of"] = str(dup) if dup is not None else None
    return out


def create_external_reference(conn: Connection, workspace_id: UUID, actor: str, *, url: str,
                              content_type: str | None = None, original_filename: str | None = None,
                              **meta: Any) -> dict[str, Any]:
    """Register a reference to a file OneStats does not own. OneStats stores only the reference and never
    fetches, modifies or deletes the external original."""
    if not (url or "").strip():
        raise ValueError("url_required")
    aid = _insert(conn, workspace_id, actor, storage_provider="external", storage_locator=url.strip(),
                  original_filename=original_filename, content_type=content_type, **meta)
    audit.write_audit(conn, workspace_id, actor, "media.external_referenced", entity="media_asset",
                      entity_id=str(aid), after={"url": url})
    return get_asset(conn, aid)


def _insert(conn: Connection, workspace_id: UUID, actor: str, *, storage_provider: str,
            storage_locator: str | None, original_filename: str | None, content_type: str | None,
            file_bytes: int | None = None, sha256: str | None = None, thumbnail_ref: str | None = None,
            preview_ref: str | None = None, **meta: Any) -> UUID:
    cols = ["workspace_id", "storage_provider", "storage_locator", "original_filename", "content_type",
            "file_bytes", "sha256", "thumbnail_ref", "preview_ref", "created_by"]
    vals = [":w", ":sp", ":loc", ":fn", ":ct", ":fb", ":sha", ":th", ":pv", ":by"]
    params: dict[str, Any] = {"w": workspace_id, "sp": storage_provider, "loc": storage_locator,
                              "fn": original_filename, "ct": content_type, "fb": file_bytes, "sha": sha256,
                              "th": thumbnail_ref, "pv": preview_ref, "by": actor}
    for k in _META_COLS:
        if k in meta and meta[k] is not None:
            cols.append(k)
            vals.append(f":{k}")
            params[k] = meta[k]
    return conn.execute(
        text(f"INSERT INTO media_asset({', '.join(cols)}) VALUES ({', '.join(vals)}) RETURNING id"),
        params,
    ).scalar_one()


def get_asset(conn: Connection, asset_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text("SELECT * FROM media_asset WHERE id = :id"), {"id": asset_id}).mappings().first()
    return dict(r) if r else None


def list_assets(conn: Connection, workspace_id: UUID, *, kind: str | None = None, limit: int = 200,
                offset: int = 0) -> list[dict[str, Any]]:
    sql = "SELECT * FROM media_asset WHERE workspace_id = :w"
    params: dict[str, Any] = {"w": workspace_id, "lim": limit, "off": offset}
    if kind is not None:
        sql += " AND kind = :k"
        params["k"] = kind
    sql += " ORDER BY created_at DESC, id LIMIT :lim OFFSET :off"
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def update_metadata(conn: Connection, workspace_id: UUID, actor: str, asset_id: UUID, **fields: Any) -> dict[str, Any]:
    current = get_asset(conn, asset_id)
    if current is None:
        raise ValueError("asset_not_found")
    if "visibility" in fields and fields["visibility"] not in ("private", "workspace", "publishable"):
        raise ValueError("invalid_visibility")
    # Publication clearance is explicit and guarded: internal access never implies permission to publish.
    # An asset cannot be made publication-eligible while it is junior-protected or sensitive, or without a
    # recorded copyright status (deliverables 20.4, 24, 33). Publishing phases still re-check this.
    def _eff(key: str) -> Any:
        return fields[key] if key in fields and fields[key] is not None else current.get(key)
    if _eff("publication_eligible"):
        if _eff("junior_protected"):
            raise ValueError("publication_blocked_junior")
        if _eff("sensitive"):
            raise ValueError("publication_blocked_sensitive")
        if not _eff("copyright_status"):
            raise ValueError("publication_requires_copyright")
    sets, params = [], {"id": asset_id}
    for k in _META_COLS:
        if k in fields and fields[k] is not None:
            sets.append(f"{k} = :{k}")
            params[k] = fields[k]
    if sets:
        sets.append("updated_at = now()")
        conn.execute(text(f"UPDATE media_asset SET {', '.join(sets)} WHERE id = :id"), params)
        audit.write_audit(conn, workspace_id, actor, "media.metadata_updated", entity="media_asset",
                          entity_id=str(asset_id), after={k: params[k] for k in params if k != "id"})
    return get_asset(conn, asset_id)


def publishable_assets(conn: Connection, workspace_id: UUID) -> list[dict[str, Any]]:
    """Only assets explicitly cleared for publication: publication-eligible, visibility 'publishable',
    not junior-protected, not sensitive, with a recorded copyright status. This is what a future website/
    portal (Phase 29) may expose — internal assets are never published by default."""
    rows = conn.execute(
        text("SELECT * FROM media_asset WHERE workspace_id = :w AND publication_eligible = true "
             "AND visibility = 'publishable' AND junior_protected = false AND sensitive = false "
             "AND copyright_status IS NOT NULL ORDER BY created_at DESC"),
        {"w": workspace_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def asset_bytes(settings: Settings, workspace_id: UUID, asset: dict[str, Any]) -> bytes:
    provider = providers.get_provider(asset["storage_provider"])
    return provider.get(settings, workspace_id, asset["storage_locator"])


def link_asset(conn: Connection, workspace_id: UUID, actor: str, asset_id: UUID, *, entity_type: str,
               entity_id: UUID, role: str | None = None) -> dict[str, Any]:
    if entity_type not in LINK_ENTITY_TYPES:
        raise ValueError("invalid_entity_type")
    lid = conn.execute(
        text("INSERT INTO media_link(workspace_id, media_asset_id, entity_type, entity_id, role, created_by) "
             "VALUES (:w, :a, :et, :eid, :r, :by) ON CONFLICT ON CONSTRAINT uq_media_link "
             "DO UPDATE SET role = COALESCE(:r, media_link.role) RETURNING id"),
        {"w": workspace_id, "a": asset_id, "et": entity_type, "eid": entity_id, "r": role, "by": actor},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "media.linked", entity="media_link", entity_id=str(lid),
                      after={"asset_id": str(asset_id), "entity_type": entity_type, "entity_id": str(entity_id)})
    r = conn.execute(text("SELECT * FROM media_link WHERE id = :id"), {"id": lid}).mappings().first()
    return dict(r)


def list_assets_for_entity(conn: Connection, workspace_id: UUID, entity_type: str, entity_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("SELECT a.*, l.role AS link_role FROM media_link l JOIN media_asset a ON a.id = l.media_asset_id "
             "WHERE l.workspace_id = :w AND l.entity_type = :et AND l.entity_id = :eid ORDER BY a.created_at"),
        {"w": workspace_id, "et": entity_type, "eid": entity_id},
    ).mappings().all()
    return [dict(r) for r in rows]
