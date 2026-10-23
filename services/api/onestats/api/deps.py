"""Shared API dependencies: session authentication and authorisation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status

from onestats.core.config import Settings, get_settings
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import auth, permissions

SettingsDep = Annotated[Settings, Depends(get_settings)]


def bearer_token(authorization: Annotated[str | None, Header()] = None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


BearerToken = Annotated[str | None, Depends(bearer_token)]


def get_current_user(token: BearerToken, settings: SettingsDep) -> dict[str, Any]:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    engine = get_engine(settings)
    if engine is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    with engine.begin() as conn:
        user = auth.validate_session(conn, token)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
    return user


CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]


def require_super_admin(user: CurrentUser) -> dict[str, Any]:
    if not user.get("is_super_admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Super Administrator required")
    return user


def get_workspace_id(
    request: Request,
    x_workspace_id: Annotated[str | None, Header()] = None,
) -> UUID:
    # Prefer the path's {workspace_id}; fall back to the X-Workspace-Id header.
    raw = request.path_params.get("workspace_id") or x_workspace_id
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing workspace id")
    try:
        return UUID(str(raw))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid workspace id") from exc


WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


@dataclass
class RequestContext:
    """Resolved per-request context for a workspace-scoped, permissioned operation."""

    user: dict[str, Any]
    workspace_id: UUID
    permissions: set[str]


def require_permission(permission: str) -> Callable[..., RequestContext]:
    """Dependency factory: require ``permission`` in the target workspace.

    The Super Administrator passes for any workspace. A non-member (or a member lacking the
    permission) gets 403. Permission resolution runs inside the workspace transaction so RLS
    scopes membership/role rows to that workspace.
    """

    def _dep(user: CurrentUser, workspace_id: WorkspaceId, settings: SettingsDep) -> RequestContext:
        engine = get_engine(settings)
        if engine is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
        with workspace_transaction(engine, workspace_id) as conn:
            perms = permissions.effective_permissions(
                conn, user["id"], workspace_id, user["is_super_admin"]
            )
        if permission not in perms:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Permission required: {permission}"
            )
        return RequestContext(user=user, workspace_id=workspace_id, permissions=perms)

    return _dep
