"""Media Archive API (Phase 11). Workspace-scoped, gated by ``media.manage``, audited.

Upload/preserve originals (internal provider), register external references, organise and link media,
and serve originals/thumbnails. OneVault is optional and capability-detected — never claimed operational
until a verified API is configured. Internal access never implies publication permission.
"""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain.media import assets, backup, heritage, integration, migration, providers

router = APIRouter(prefix="/workspaces/{workspace_id}/media", tags=["media"])
Ctx = Annotated[RequestContext, Depends(require_permission("media.manage"))]

_ERRORS = {
    "url_required": status.HTTP_400_BAD_REQUEST,
    "invalid_visibility": status.HTTP_400_BAD_REQUEST,
    "invalid_entity_type": status.HTTP_400_BAD_REQUEST,
    "asset_not_found": status.HTTP_404_NOT_FOUND,
    "unknown_provider": status.HTTP_400_BAD_REQUEST,
    "cannot_migrate_external": status.HTTP_400_BAD_REQUEST,
    "cannot_migrate_to_external": status.HTTP_400_BAD_REQUEST,
    "source_integrity_failed": status.HTTP_409_CONFLICT,
    "migration_verify_failed": status.HTTP_409_CONFLICT,
    "publication_blocked_junior": status.HTTP_409_CONFLICT,
    "publication_blocked_sensitive": status.HTTP_409_CONFLICT,
    "publication_requires_copyright": status.HTTP_409_CONFLICT,
    "name_required": status.HTTP_400_BAD_REQUEST,
    "collection_not_found": status.HTTP_404_NOT_FOUND,
    "item_not_found": status.HTTP_404_NOT_FOUND,
    "item_has_no_asset": status.HTTP_409_CONFLICT,
    "asset_not_cleared_for_publication": status.HTTP_409_CONFLICT,
    "source_not_found": status.HTTP_404_NOT_FOUND,
    "source_has_no_file": status.HTTP_409_CONFLICT,
    "source_file_missing": status.HTTP_409_CONFLICT,
    "source_integrity_failed": status.HTTP_409_CONFLICT,
}


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


def _err(exc: ValueError) -> HTTPException:
    return HTTPException(_ERRORS.get(str(exc), status.HTTP_400_BAD_REQUEST), str(exc))


def _s(d: dict[str, Any]) -> dict[str, Any]:
    return {k: (str(v) if isinstance(v, UUID) else v) for k, v in d.items()}


class ExternalRef(BaseModel):
    url: str
    content_type: str | None = None
    original_filename: str | None = None
    kind: str = "document"
    title: str | None = None
    description: str | None = None
    copyright_status: str | None = None
    licence: str | None = None
    attribution: str | None = None


class MetadataUpdate(BaseModel):
    kind: str | None = None
    title: str | None = None
    description: str | None = None
    caption: str | None = None
    copyright_status: str | None = None
    licence: str | None = None
    attribution: str | None = None
    source_provenance: str | None = None
    visibility: str | None = Field(default=None, pattern="^(private|workspace|publishable)$")
    publication_eligible: bool | None = None
    sensitive: bool | None = None
    junior_protected: bool | None = None


class LinkBody(BaseModel):
    entity_type: str = Field(pattern="^(match|person|research_source|season|organisation|team|other)$")
    entity_id: UUID
    role: str | None = None


@router.get("/providers")
def list_providers(workspace_id: UUID, settings: SettingsDep, ctx: Ctx) -> list[dict[str, Any]]:
    return providers.describe_providers(settings)


@router.get("/assets")
def list_assets(workspace_id: UUID, settings: SettingsDep, ctx: Ctx, kind: str | None = None,
                limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_s(r) for r in assets.list_assets(conn, workspace_id, kind=kind, limit=limit, offset=offset)]


@router.post("/assets", status_code=status.HTTP_201_CREATED)
async def upload_asset(workspace_id: UUID, settings: SettingsDep, ctx: Ctx, file: UploadFile,
                       kind: str = "document", title: str | None = None) -> dict[str, Any]:
    raw = await file.read()
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty_file")
    if len(raw) > settings.max_media_bytes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "file_too_large")
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return _s(assets.create_internal_asset(conn, settings, workspace_id, str(ctx.user["id"]), raw=raw,
                                               content_type=file.content_type or "application/octet-stream",
                                               original_filename=file.filename, kind=kind, title=title))


@router.get("/assets/publishable")
def publishable(workspace_id: UUID, settings: SettingsDep, ctx: Ctx) -> list[dict[str, Any]]:
    """Assets explicitly cleared for publication (future website/portal). Internal access alone never
    makes an asset publishable; junior-protected/sensitive assets are excluded."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_s(r) for r in assets.publishable_assets(conn, workspace_id)]


@router.post("/assets/external", status_code=status.HTTP_201_CREATED)
def add_external(workspace_id: UUID, body: ExternalRef, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(assets.create_external_reference(conn, workspace_id, str(ctx.user["id"]), **body.model_dump()))
        except ValueError as exc:
            raise _err(exc) from exc


@router.get("/assets/{asset_id}")
def get_asset(workspace_id: UUID, asset_id: UUID, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        a = assets.get_asset(conn, asset_id)
        if a is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "asset_not_found")
        return _s(a)


@router.patch("/assets/{asset_id}")
def update_asset(workspace_id: UUID, asset_id: UUID, body: MetadataUpdate, settings: SettingsDep,
                 ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(assets.update_metadata(conn, workspace_id, str(ctx.user["id"]), asset_id,
                                            **body.model_dump(exclude_none=True)))
        except ValueError as exc:
            raise _err(exc) from exc


def _serve(settings, workspace_id: UUID, asset: dict[str, Any], locator: str | None):
    if asset["storage_provider"] != "internal":
        raise HTTPException(status.HTTP_409_CONFLICT, "not_internal")   # external/onevault: use storage_locator
    if not locator:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no_file")
    path = providers.internal_provider().path(settings, workspace_id, locator)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no_file")
    return FileResponse(str(path))


@router.get("/assets/{asset_id}/file")
def get_file(workspace_id: UUID, asset_id: UUID, settings: SettingsDep, ctx: Ctx):
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        a = assets.get_asset(conn, asset_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "asset_not_found")
    return _serve(settings, workspace_id, a, a.get("storage_locator"))


@router.get("/assets/{asset_id}/thumbnail")
def get_thumbnail(workspace_id: UUID, asset_id: UUID, settings: SettingsDep, ctx: Ctx):
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        a = assets.get_asset(conn, asset_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "asset_not_found")
    return _serve(settings, workspace_id, a, a.get("thumbnail_ref"))


class MigrateBody(BaseModel):
    to_provider: str = Field(pattern="^(internal|onevault|external)$")
    remove_source: bool = False


@router.get("/assets/{asset_id}/verify")
def verify_asset(workspace_id: UUID, asset_id: UUID, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        a = assets.get_asset(conn, asset_id)
        if a is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "asset_not_found")
    return migration.verify_asset(settings, workspace_id, a)


@router.post("/assets/{asset_id}/migrate")
def migrate_asset(workspace_id: UUID, asset_id: UUID, body: MigrateBody, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(migration.migrate_asset(conn, settings, workspace_id, str(ctx.user["id"]), asset_id,
                                              to_provider=body.to_provider, remove_source=body.remove_source))
        except providers.ProviderUnavailable as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        except ValueError as exc:
            raise _err(exc) from exc


@router.post("/assets/{asset_id}/link")
def link_asset(workspace_id: UUID, asset_id: UUID, body: LinkBody, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(assets.link_asset(conn, workspace_id, str(ctx.user["id"]), asset_id,
                                       entity_type=body.entity_type, entity_id=body.entity_id, role=body.role))
        except ValueError as exc:
            raise _err(exc) from exc


class CollectionCreate(BaseModel):
    name: str
    description: str | None = None


class ItemCreate(BaseModel):
    media_asset_id: UUID | None = None
    title: str | None = None
    significance: str | None = None
    description: str | None = None
    display_order: int = 0


class ItemUpdate(BaseModel):
    title: str | None = None
    significance: str | None = None
    description: str | None = None
    display_order: int | None = None
    publication_eligible: bool | None = None


@router.get("/heritage/collections")
def list_collections(workspace_id: UUID, settings: SettingsDep, ctx: Ctx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_s(r) for r in heritage.list_collections(conn, workspace_id)]


@router.post("/heritage/collections", status_code=status.HTTP_201_CREATED)
def create_collection(workspace_id: UUID, body: CollectionCreate, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(heritage.create_collection(conn, workspace_id, str(ctx.user["id"]), **body.model_dump()))
        except ValueError as exc:
            raise _err(exc) from exc


@router.get("/heritage/collections/{collection_id}/items")
def list_items(workspace_id: UUID, collection_id: UUID, settings: SettingsDep, ctx: Ctx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_s(r) for r in heritage.list_items(conn, workspace_id, collection_id)]


@router.post("/heritage/collections/{collection_id}/items", status_code=status.HTTP_201_CREATED)
def add_item(workspace_id: UUID, collection_id: UUID, body: ItemCreate, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(heritage.add_item(conn, workspace_id, str(ctx.user["id"]), collection_id, **body.model_dump()))
        except ValueError as exc:
            raise _err(exc) from exc


@router.patch("/heritage/items/{item_id}")
def update_item(workspace_id: UUID, item_id: UUID, body: ItemUpdate, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(heritage.update_item(conn, workspace_id, str(ctx.user["id"]), item_id,
                                          **body.model_dump(exclude_none=True)))
        except ValueError as exc:
            raise _err(exc) from exc


@router.post("/from-research-source/{source_id}", status_code=status.HTTP_201_CREATED)
def promote_research_source(workspace_id: UUID, source_id: UUID, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    """Promote a Phase 10 research document into a canonical media asset (moves the file; no duplicate)."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return _s(integration.promote_research_source(conn, settings, workspace_id, str(ctx.user["id"]), source_id))
        except ValueError as exc:
            raise _err(exc) from exc


@router.get("/backup/verify")
def backup_verify(workspace_id: UUID, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    """Integrity scan: missing-file detection + checksum validation across the archive."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return backup.verify_media(conn, settings, workspace_id)


@router.get("/backup/manifest")
def backup_manifest(workspace_id: UUID, settings: SettingsDep, ctx: Ctx) -> dict[str, Any]:
    """A validatable backup manifest (assets + checksums + relationships + heritage)."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return backup.build_manifest(conn, settings, workspace_id)


@router.get("/entities/{entity_type}/{entity_id}/assets")
def entity_assets(workspace_id: UUID, entity_type: str, entity_id: UUID, settings: SettingsDep,
                  ctx: Ctx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return [_s(r) for r in assets.list_assets_for_entity(conn, workspace_id, entity_type, entity_id)]
