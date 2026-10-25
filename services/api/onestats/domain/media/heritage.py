"""Club Heritage Collection (Phase 11, Stage 11.7).

Curated collections of media assets with historical significance markers and descriptions, for optional
future website publication (Phase 29). Publication remains an explicit, permission-controlled decision —
nothing is published by default, and an item is only publishable when its underlying asset is cleared.
Workspace-scoped (FORCE RLS); audited.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.domain import audit


def create_collection(conn: Connection, workspace_id: UUID, actor: str, *, name: str,
                      description: str | None = None) -> dict[str, Any]:
    if not (name or "").strip():
        raise ValueError("name_required")
    cid = conn.execute(
        text("INSERT INTO heritage_collection(workspace_id, name, description, created_by) "
             "VALUES (:w, :n, :d, :by) RETURNING id"),
        {"w": workspace_id, "n": name, "d": description, "by": actor},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "media.heritage_collection_created", entity="heritage_collection",
                      entity_id=str(cid), after={"name": name})
    return get_collection(conn, cid)


def get_collection(conn: Connection, collection_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text("SELECT * FROM heritage_collection WHERE id = :id"), {"id": collection_id}).mappings().first()
    return dict(r) if r else None


def list_collections(conn: Connection, workspace_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("SELECT c.*, (SELECT count(*) FROM heritage_item i WHERE i.collection_id = c.id) AS items "
             "FROM heritage_collection c WHERE c.workspace_id = :w ORDER BY c.name"),
        {"w": workspace_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def add_item(conn: Connection, workspace_id: UUID, actor: str, collection_id: UUID, *,
             media_asset_id: UUID | None = None, title: str | None = None, significance: str | None = None,
             description: str | None = None, display_order: int = 0) -> dict[str, Any]:
    if get_collection(conn, collection_id) is None:
        raise ValueError("collection_not_found")
    iid = conn.execute(
        text("INSERT INTO heritage_item(workspace_id, collection_id, media_asset_id, title, significance, "
             "description, display_order, created_by) VALUES (:w, :c, :m, :t, :sig, :d, :ord, :by) RETURNING id"),
        {"w": workspace_id, "c": collection_id, "m": media_asset_id, "t": title, "sig": significance,
         "d": description, "ord": display_order, "by": actor},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "media.heritage_item_added", entity="heritage_item",
                      entity_id=str(iid), after={"collection_id": str(collection_id)})
    return get_item(conn, iid)


def get_item(conn: Connection, item_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text("SELECT * FROM heritage_item WHERE id = :id"), {"id": item_id}).mappings().first()
    return dict(r) if r else None


def list_items(conn: Connection, workspace_id: UUID, collection_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("SELECT * FROM heritage_item WHERE workspace_id = :w AND collection_id = :c "
             "ORDER BY display_order, created_at"),
        {"w": workspace_id, "c": collection_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def update_item(conn: Connection, workspace_id: UUID, actor: str, item_id: UUID, *, title: str | None = None,
                significance: str | None = None, description: str | None = None,
                display_order: int | None = None, publication_eligible: bool | None = None) -> dict[str, Any]:
    item = get_item(conn, item_id)
    if item is None:
        raise ValueError("item_not_found")
    # An item may be marked publication-eligible only when its underlying asset is itself cleared for
    # publication — heritage curation never overrides the asset-level publication guard.
    if publication_eligible:
        if item["media_asset_id"] is None:
            raise ValueError("item_has_no_asset")
        cleared = conn.execute(
            text("SELECT publication_eligible AND visibility = 'publishable' AND junior_protected = false "
                 "AND sensitive = false AND copyright_status IS NOT NULL FROM media_asset WHERE id = :a"),
            {"a": item["media_asset_id"]},
        ).scalar_one_or_none()
        if not cleared:
            raise ValueError("asset_not_cleared_for_publication")
    sets, params = [], {"id": item_id}
    for col, val in (("title", title), ("significance", significance), ("description", description),
                     ("display_order", display_order), ("publication_eligible", publication_eligible)):
        if val is not None:
            sets.append(f"{col} = :{col}")
            params[col] = val
    if sets:
        sets.append("updated_at = now()")
        conn.execute(text(f"UPDATE heritage_item SET {', '.join(sets)} WHERE id = :id"), params)
        audit.write_audit(conn, workspace_id, actor, "media.heritage_item_updated", entity="heritage_item",
                          entity_id=str(item_id), after={k: params[k] for k in params if k != "id"})
    return get_item(conn, item_id)
