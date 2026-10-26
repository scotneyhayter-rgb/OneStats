"""System Administration — user management endpoints (Super-Admin only).

Create/edit/suspend accounts, issue temporary single-use passwords, invitations (create/list/revoke/
accept), assign system & workspace roles (cross-workspace), and view a user's login/admin history. Every
mutating endpoint is Super-Admin-gated (backend enforcement); escalation guards live in the domain.
"""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from onestats.api.deps import SettingsDep, require_super_admin
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import audit, permissions, users

router = APIRouter(tags=["user-admin"])
SuperAdmin = Annotated[dict, Depends(require_super_admin)]

_ERRORS = {
    "username_taken": status.HTTP_409_CONFLICT,
    "user_not_found": status.HTTP_404_NOT_FOUND,
    "invalid_status": status.HTTP_400_BAD_REQUEST,
    "cannot_suspend_last_super_admin": status.HTTP_409_CONFLICT,
    "cannot_demote_last_super_admin": status.HTTP_409_CONFLICT,
    "cannot_grant_super_admin": status.HTTP_400_BAD_REQUEST,
    "invitation_not_found": status.HTTP_404_NOT_FOUND,
    "invalid_or_expired_invitation": status.HTTP_400_BAD_REQUEST,
}


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


def _err(exc: ValueError) -> HTTPException:
    return HTTPException(_ERRORS.get(str(exc), status.HTTP_400_BAD_REQUEST), str(exc))


class CreateUser(BaseModel):
    username: str = Field(min_length=3, max_length=150)
    display_name: str | None = Field(default=None, max_length=200)
    is_super_admin: bool = False


class UpdateUser(BaseModel):
    display_name: str | None = None
    status: str | None = Field(default=None, pattern="^(active|suspended)$")
    is_super_admin: bool | None = None


class WorkspaceRole(BaseModel):
    workspace_id: UUID
    role: str = Field(min_length=1, max_length=50)


class AcceptInvite(BaseModel):
    token: str = Field(min_length=10)
    new_password: str = Field(min_length=1, max_length=256)


@router.get("/users")
def list_users(admin: SuperAdmin, settings: SettingsDep) -> list[dict[str, Any]]:
    with _engine(settings).begin() as conn:
        return users.list_users(conn)


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(body: CreateUser, admin: SuperAdmin, settings: SettingsDep) -> dict[str, Any]:
    with _engine(settings).begin() as conn:
        try:
            return users.create_user(conn, str(admin["id"]), username=body.username,
                                     display_name=body.display_name, is_super_admin=body.is_super_admin)
        except ValueError as exc:
            raise _err(exc) from exc


@router.patch("/users/{user_id}")
def update_user(user_id: UUID, body: UpdateUser, admin: SuperAdmin, settings: SettingsDep) -> dict[str, Any]:
    with _engine(settings).begin() as conn:
        try:
            if body.display_name is not None:
                users.update_display_name(conn, str(admin["id"]), user_id, body.display_name)
            if body.status is not None:
                users.set_status(conn, str(admin["id"]), user_id, body.status)
            if body.is_super_admin is not None:
                users.set_super_admin(conn, str(admin["id"]), user_id, body.is_super_admin)
        except ValueError as exc:
            raise _err(exc) from exc
    return {"updated": True}


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: UUID, admin: SuperAdmin, settings: SettingsDep) -> dict[str, Any]:
    with _engine(settings).begin() as conn:
        try:
            return users.issue_temp_password(conn, str(admin["id"]), user_id)
        except ValueError as exc:
            raise _err(exc) from exc


@router.get("/users/{user_id}/audit")
def user_audit(user_id: UUID, admin: SuperAdmin, settings: SettingsDep) -> dict[str, Any]:
    with _engine(settings).begin() as conn:
        return users.user_audit(conn, user_id)


@router.post("/users/{user_id}/workspace-roles", status_code=status.HTTP_201_CREATED)
def assign_workspace_role(user_id: UUID, body: WorkspaceRole, admin: SuperAdmin, settings: SettingsDep) -> dict[str, Any]:
    """Assign a user to a workspace with a role (cross-workspace, Super-Admin). 'super_admin' is rejected."""
    with workspace_transaction(_engine(settings), body.workspace_id) as conn:
        try:
            permissions.grant_role(conn, user_id, body.workspace_id, body.role)
        except ValueError as exc:
            raise _err(exc) from exc
        audit.write_audit(conn, body.workspace_id, str(admin["id"]), "membership.grant",
                          entity="app_user", entity_id=str(user_id), after={"role": body.role})
    return {"granted": True}


@router.delete("/users/{user_id}/workspace-roles")
def revoke_workspace_role(user_id: UUID, body: WorkspaceRole, admin: SuperAdmin, settings: SettingsDep) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), body.workspace_id) as conn:
        permissions.revoke_role(conn, user_id, body.workspace_id, body.role)
        audit.write_audit(conn, body.workspace_id, str(admin["id"]), "membership.revoke",
                          entity="app_user", entity_id=str(user_id), after={"role": body.role})
    return {"revoked": True}


# --- invitations ---
@router.get("/invitations")
def list_invitations(admin: SuperAdmin, settings: SettingsDep) -> list[dict[str, Any]]:
    with _engine(settings).begin() as conn:
        return users.list_invitations(conn)


@router.post("/invitations", status_code=status.HTTP_201_CREATED)
def create_invitation(body: CreateUser, admin: SuperAdmin, settings: SettingsDep) -> dict[str, Any]:
    with _engine(settings).begin() as conn:
        try:
            return users.create_invitation(conn, str(admin["id"]), username=body.username,
                                           display_name=body.display_name, is_super_admin=body.is_super_admin)
        except ValueError as exc:
            raise _err(exc) from exc


@router.post("/invitations/{invitation_id}/revoke")
def revoke_invitation(invitation_id: UUID, admin: SuperAdmin, settings: SettingsDep) -> dict[str, Any]:
    with _engine(settings).begin() as conn:
        try:
            users.revoke_invitation(conn, str(admin["id"]), invitation_id)
        except ValueError as exc:
            raise _err(exc) from exc
    return {"revoked": True}


@router.post("/invitations/accept", status_code=status.HTTP_201_CREATED)
def accept_invitation(body: AcceptInvite, settings: SettingsDep) -> dict[str, Any]:
    """Public: an invitee sets their password via the single-use token to activate their account."""
    from onestats.core import security
    err = security.password_strength_error(body.new_password)
    if err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, err)
    with _engine(settings).begin() as conn:
        try:
            return users.accept_invitation(conn, body.token, body.new_password)
        except ValueError as exc:
            raise _err(exc) from exc
