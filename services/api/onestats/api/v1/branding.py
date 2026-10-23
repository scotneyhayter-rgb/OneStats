"""Workspace branding endpoints: colours, preview, reset, and secure logo handling."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from onestats.api.deps import CurrentUser, SettingsDep, require_permission
from onestats.core import color, images
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import branding, logos, workspaces

router = APIRouter(prefix="/workspaces/{workspace_id}/branding", tags=["branding"])

ManageCtx = Annotated[Any, Depends(require_permission("branding.manage"))]


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


class BrandingUpdate(BaseModel):
    primary_colour: str | None = None
    secondary_colour: str | None = None
    third_colour: str | None = None
    fourth_colour: str | None = None
    accent_colour: str | None = None
    theme_mode: str | None = None
    tagline: str | None = Field(default=None, max_length=200)
    background: dict[str, Any] | None = None
    presets: list[dict[str, Any]] | None = None


class PreviewRequest(BaseModel):
    colours: dict[str, str] = Field(default_factory=dict)


@router.get("")
def get_branding(workspace_id: UUID, user: CurrentUser, settings: SettingsDep) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id, user["id"]) as conn:
        if not user["is_super_admin"] and not workspaces.user_is_member(conn, user["id"], workspace_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this workspace")
        b = branding.get_branding(conn, workspace_id)
    return {
        "branding": b,
        "resolved": branding.resolve_tokens(b),
        "published": branding.published_payload(workspace_id, b),
    }


@router.put("")
def set_branding(
    workspace_id: UUID, body: BrandingUpdate, settings: SettingsDep, ctx: ManageCtx
) -> dict[str, Any]:
    fields = body.model_dump(exclude_unset=True)
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            after = branding.set_branding(conn, workspace_id, ctx.user["id"], fields)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"branding": after, "resolved": branding.resolve_tokens(after)}


@router.post("/preview")
def preview(workspace_id: UUID, body: PreviewRequest, ctx: ManageCtx) -> dict[str, Any]:
    """Resolve accessible foregrounds + AA warnings for candidate colours WITHOUT saving."""
    out: dict[str, Any] = {"colours": {}, "warnings": []}
    for key, val in body.colours.items():
        if not color.is_valid_hex(val):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"invalid_colour:{key}")
        res = color.resolve(val)
        out["colours"][key] = res
        if not res["meets_aa"]:
            out["warnings"].append(f"{key} ({val}) cannot reach WCAG AA with black or white text")
    return out


@router.post("/reset", status_code=status.HTTP_200_OK)
def reset(workspace_id: UUID, settings: SettingsDep, ctx: ManageCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        branding.reset_branding(conn, workspace_id, ctx.user["id"])
    return {"reset": True}


@router.post("/logo", status_code=status.HTTP_201_CREATED)
async def upload_logo(
    workspace_id: UUID, settings: SettingsDep, ctx: ManageCtx, file: UploadFile
) -> dict[str, Any]:
    raw = await file.read()
    try:
        stored = logos.store_logo(settings, workspace_id, raw, file.content_type or "")
    except images.ImageError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        branding.set_branding(conn, workspace_id, ctx.user["id"], {"logo_ref": stored["logo_ref"]})
    return stored


@router.delete("/logo", status_code=status.HTTP_200_OK)
def delete_logo(workspace_id: UUID, settings: SettingsDep, ctx: ManageCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        b = branding.get_branding(conn, workspace_id)
        ref = (b or {}).get("logo_ref")
        if ref:
            logos.remove_logo(settings, workspace_id, ref)
            branding.set_branding(conn, workspace_id, ctx.user["id"], {"logo_ref": None})
    return {"removed": True}


@router.get("/logo")
def get_logo(workspace_id: UUID, user: CurrentUser, settings: SettingsDep):
    with workspace_transaction(_engine(settings), workspace_id, user["id"]) as conn:
        if not user["is_super_admin"] and not workspaces.user_is_member(conn, user["id"], workspace_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this workspace")
        b = branding.get_branding(conn, workspace_id)
    ref = (b or {}).get("logo_ref")
    path = logos.logo_path(settings, workspace_id, ref) if ref else None
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no_logo")
    return FileResponse(str(path))
