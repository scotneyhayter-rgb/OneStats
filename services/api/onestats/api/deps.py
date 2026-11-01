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
    #: the permission that authorised this request (Part 6: effective permission used)
    permission: str | None = None
    #: the actor's role(s) in this workspace, comma-joined; "super_admin" when acting as platform admin
    actor_role: str | None = None
    #: True when a platform Super Admin is operating in a workspace they are not an ordinary member of
    acting_as_super_admin: bool = False
    #: per-request id stamped by the request_id middleware
    request_id: str | None = None

    def audit_kwargs(self, reason: str | None = None) -> dict[str, Any]:
        """Keyword arguments for ``audit.write_audit`` capturing WHO really acted and HOW.

        The actor is always the real authenticated user id — a Super Admin is never recorded as
        the local Organisation Admin. Pass a ``reason`` for sensitive changes."""
        return {
            "actor_role": self.actor_role,
            "effective_permission": self.permission,
            "reason": reason,
            "request_id": self.request_id,
            "acting_as_super_admin": self.acting_as_super_admin,
        }


def require_permission(permission: str) -> Callable[..., RequestContext]:
    """Dependency factory: require ``permission`` in the target workspace.

    The Super Administrator passes for any workspace. A non-member (or a member lacking the
    permission) gets 403. Permission resolution runs inside the workspace transaction so RLS
    scopes membership/role rows to that workspace.
    """

    def _dep(
        request: Request, user: CurrentUser, workspace_id: WorkspaceId, settings: SettingsDep
    ) -> RequestContext:
        engine = get_engine(settings)
        if engine is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
        is_super = bool(user["is_super_admin"])
        with workspace_transaction(engine, workspace_id) as conn:
            perms = permissions.effective_permissions(conn, user["id"], workspace_id, is_super)
            roles = permissions.user_roles(conn, user["id"], workspace_id)
        if permission not in perms:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Permission required: {permission}"
            )
        # A Super Admin with no ordinary membership is "acting as super admin" for this workspace.
        acting_as_super_admin = is_super and not roles
        actor_role = "super_admin" if acting_as_super_admin else (",".join(roles) or ("super_admin" if is_super else None))
        return RequestContext(
            user=user,
            workspace_id=workspace_id,
            permissions=perms,
            permission=permission,
            actor_role=actor_role,
            acting_as_super_admin=acting_as_super_admin,
            request_id=getattr(request.state, "request_id", None),
        )

    return _dep


def require_any_permission(*required: str) -> Callable[..., RequestContext]:
    """Dependency factory: require AT LEAST ONE of ``required`` in the target workspace.

    For reads shared by several roles — e.g. reference lists (competitions, teams, venues) that the
    scorecard-entry/approval screens need. A Scorecard Editor or Data Verifier holds ``match.manage`` /
    ``scorecard.approve`` but not the management permission, so a single ``*.manage`` gate would wrongly
    lock them out of their own workflow. Writes stay gated by the management permission. The Super
    Administrator passes for any workspace.
    """

    def _dep(
        request: Request, user: CurrentUser, workspace_id: WorkspaceId, settings: SettingsDep
    ) -> RequestContext:
        engine = get_engine(settings)
        if engine is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
        is_super = bool(user["is_super_admin"])
        with workspace_transaction(engine, workspace_id) as conn:
            perms = permissions.effective_permissions(conn, user["id"], workspace_id, is_super)
            roles = permissions.user_roles(conn, user["id"], workspace_id)
        held = next((p for p in required if p in perms), None)
        if held is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Permission required: {' or '.join(required)}"
            )
        acting_as_super_admin = is_super and not roles
        actor_role = "super_admin" if acting_as_super_admin else (",".join(roles) or ("super_admin" if is_super else None))
        return RequestContext(
            user=user,
            workspace_id=workspace_id,
            permissions=perms,
            permission=held,
            actor_role=actor_role,
            acting_as_super_admin=acting_as_super_admin,
            request_id=getattr(request.state, "request_id", None),
        )

    return _dep
