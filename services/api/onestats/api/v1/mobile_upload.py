"""Mobile upload endpoints (deliverable 20a).

Two surfaces:
- **Pairing** (`/workspaces/{workspace_id}/mobile-upload/*`): an authenticated desktop user with
  ``media.manage`` starts/lists/revokes short-lived pairing sessions. Creating one returns the raw token
  **once** plus the relative upload path, which the desktop composes into a LAN URL + QR.
- **Upload** (`/upload/{workspace_id}/{session_id}`): the phone posts files authenticated by the pairing
  **token** (``X-Upload-Token`` header), not a bearer session — no long-lived credential lands on the phone.
  The workspace comes from the paired URL so RLS scopes the session lookup; the token proves the pairing.

Uploaded files are type-verified and size-limited, stored as preserved originals, and left unassigned for
the media review queue. Nothing is auto-published.
"""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import mobile_upload

# authenticated pairing surface (desktop) — media-upload permission
pairing_router = APIRouter(prefix="/workspaces/{workspace_id}/mobile-upload", tags=["mobile-upload"])
PairCtx = Annotated[RequestContext, Depends(require_permission("media.manage"))]

# token-authenticated upload surface (phone) — NO bearer session
upload_router = APIRouter(prefix="/upload", tags=["mobile-upload"])

_ERRORS = {
    "session_not_found": status.HTTP_404_NOT_FOUND,
    "empty_file": status.HTTP_400_BAD_REQUEST,
    "file_too_large": status.HTTP_400_BAD_REQUEST,
    "unsupported_file_type": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
}


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


def _err(exc: ValueError) -> HTTPException:
    return HTTPException(_ERRORS.get(str(exc), status.HTTP_400_BAD_REQUEST), str(exc))


class CreateSession(BaseModel):
    ttl_minutes: int = Field(default=mobile_upload.DEFAULT_TTL_MINUTES, ge=1, le=mobile_upload.MAX_TTL_MINUTES)
    scope: dict[str, Any] = Field(default_factory=dict)


@pairing_router.post("/sessions", status_code=status.HTTP_201_CREATED)
def create_session(workspace_id: UUID, body: CreateSession, settings: SettingsDep, ctx: PairCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        out = mobile_upload.create_session(conn, workspace_id, str(ctx.user["id"]),
                                           ttl_minutes=body.ttl_minutes, scope=body.scope)
    # the desktop composes the full LAN URL from its known host + this path, then renders the QR
    out["upload_path"] = f"/api/v1/upload/{workspace_id}/{out['id']}"
    return out


@pairing_router.get("/sessions")
def list_sessions(workspace_id: UUID, settings: SettingsDep, ctx: PairCtx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return mobile_upload.list_sessions(conn, workspace_id)


@pairing_router.post("/sessions/{session_id}/revoke")
def revoke_session(workspace_id: UUID, session_id: UUID, settings: SettingsDep, ctx: PairCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return mobile_upload.revoke_session(conn, workspace_id, str(ctx.user["id"]), session_id)
        except ValueError as exc:
            raise _err(exc) from exc


def _resolve(settings, workspace_id: UUID, session_id: UUID, token: str | None):
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing_upload_token")
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        session = mobile_upload.resolve_token(conn, workspace_id, session_id, token)
    if session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_or_expired_session")
    return session


@upload_router.get("/{workspace_id}/{session_id}")
def session_status(workspace_id: UUID, session_id: UUID, settings: SettingsDep,
                   x_upload_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """The phone checks its paired session is still valid before showing the upload form."""
    session = _resolve(settings, workspace_id, session_id, x_upload_token)
    return {"valid": True, "expires_at": session["expires_at"].isoformat() if session["expires_at"] else None,
            "upload_count": session["upload_count"]}


@upload_router.post("/{workspace_id}/{session_id}", status_code=status.HTTP_201_CREATED)
async def upload_file(workspace_id: UUID, session_id: UUID, settings: SettingsDep, file: UploadFile,
                      x_upload_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    session = _resolve(settings, workspace_id, session_id, x_upload_token)
    raw = await file.read()
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return mobile_upload.accept_upload(conn, settings, workspace_id, session, raw=raw,
                                               content_type=file.content_type, filename=file.filename)
        except ValueError as exc:
            raise _err(exc) from exc
