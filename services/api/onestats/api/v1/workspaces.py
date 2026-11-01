"""Workspace CRUD, membership, and "My Workspaces" endpoints."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text

from onestats.api.deps import CurrentUser, SettingsDep, require_permission, require_super_admin
from onestats.db.session import get_engine
from onestats.db.workspace import user_transaction, workspace_transaction
from onestats.domain import audit, my_tasks, permissions, workspaces

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

_VALUE_ERR_STATUS = {
    "duplicate_identifier": status.HTTP_409_CONFLICT,
    "workspace_not_found": status.HTTP_404_NOT_FOUND,
    "confirmation_mismatch": status.HTTP_400_BAD_REQUEST,
}


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


def _value_error(exc: ValueError) -> HTTPException:
    code = str(exc)
    return HTTPException(_VALUE_ERR_STATUS.get(code, status.HTTP_400_BAD_REQUEST), code)


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    short_name: str = Field(min_length=1, max_length=60)
    type: str = Field(default="club")


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    short_name: str | None = Field(default=None, max_length=60)
    status: str | None = None
    score_format: str | None = Field(default=None, pattern="^(au|en)$")


class MemberAdd(BaseModel):
    # Identify the user by id or by username. Username lets a workspace admin add an existing account
    # without the platform-wide user list (which is Super-Admin only).
    user_id: UUID | None = None
    username: str | None = Field(default=None, max_length=150)
    role: str

    @model_validator(mode="after")
    def _one_identifier(self) -> "MemberAdd":
        if self.user_id is None and not (self.username and self.username.strip()):
            raise ValueError("user_id_or_username_required")
        return self


class MemberRevoke(BaseModel):
    user_id: UUID
    role: str


class WorkspaceDelete(BaseModel):
    confirm_short_name: str = Field(min_length=1, max_length=60)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_workspace(
    body: WorkspaceCreate, settings: SettingsDep, admin: Annotated[dict, Depends(require_super_admin)]
) -> dict[str, Any]:
    with _engine(settings).begin() as conn:
        try:
            ws_id = workspaces.create_workspace(conn, body.name, body.short_name, body.type, admin["id"])
        except ValueError as exc:
            raise _value_error(exc) from exc
        return workspaces.get_workspace(conn, ws_id)


@router.get("")
def my_workspaces(user: CurrentUser, settings: SettingsDep) -> list[dict[str, Any]]:
    eng = _engine(settings)
    if user["is_super_admin"]:
        with eng.begin() as conn:
            return workspaces.list_for_user(conn, user["id"], True)
    with user_transaction(eng, user["id"]) as conn:
        return workspaces.list_for_user(conn, user["id"], False)


@router.get("/{workspace_id}")
def get_workspace(workspace_id: UUID, user: CurrentUser, settings: SettingsDep) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id, user["id"]) as conn:
        if not user["is_super_admin"] and not workspaces.user_is_member(conn, user["id"], workspace_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this workspace")
        ws = workspaces.get_workspace(conn, workspace_id)
    if ws is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "workspace_not_found")
    return ws


@router.patch("/{workspace_id}")
def update_workspace(
    workspace_id: UUID,
    body: WorkspaceUpdate,
    settings: SettingsDep,
    ctx: Annotated[Any, Depends(require_permission("workspace.manage"))],
) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return workspaces.update_workspace(
                conn, workspace_id, ctx.user["id"], body.name, body.short_name, body.status,
                score_format=body.score_format,
            )
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.delete("/{workspace_id}")
def delete_workspace(
    workspace_id: UUID,
    body: WorkspaceDelete,
    settings: SettingsDep,
    admin: Annotated[dict, Depends(require_super_admin)],
) -> dict[str, Any]:
    """Permanently delete a workspace and all its data. Super-Admin only; the caller must supply the
    workspace's exact short name as confirmation (validated server-side). Irreversible."""
    with _engine(settings).begin() as conn:
        try:
            return workspaces.delete_workspace(conn, workspace_id, str(admin["id"]), body.confirm_short_name)
        except ValueError as exc:
            raise _value_error(exc) from exc


@router.post("/{workspace_id}/members", status_code=status.HTTP_201_CREATED)
def add_member(
    workspace_id: UUID,
    body: MemberAdd,
    settings: SettingsDep,
    ctx: Annotated[Any, Depends(require_permission("user.admin"))],
) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        user_id = body.user_id
        if user_id is None:
            row = conn.execute(
                text("SELECT id FROM app_user WHERE lower(username) = lower(:u) AND status = 'active'"),
                {"u": body.username.strip()},  # type: ignore[union-attr]
            ).first()
            if row is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
            user_id = row[0]
        try:
            permissions.grant_role(conn, user_id, workspace_id, body.role)
        except ValueError as exc:
            raise _value_error(exc) from exc
        audit.write_audit(
            conn, workspace_id, str(ctx.user["id"]), "membership.grant",
            entity="app_user", entity_id=str(user_id), after={"role": body.role},
            **ctx.audit_kwargs(reason=f"grant {body.role}"),
        )
    return {"granted": True, "user_id": str(user_id), "role": body.role}


@router.delete("/{workspace_id}/members")
def revoke_member(
    workspace_id: UUID,
    body: MemberRevoke,
    settings: SettingsDep,
    ctx: Annotated[Any, Depends(require_permission("user.admin"))],
) -> dict[str, Any]:
    """Revoke one workspace role from a user (workspace-scoped; held by Organisation Admins and
    Super Admins via user.admin). The platform super_admin flag is never a workspace role."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        permissions.revoke_role(conn, body.user_id, workspace_id, body.role)
        audit.write_audit(
            conn, workspace_id, str(ctx.user["id"]), "membership.revoke",
            entity="app_user", entity_id=str(body.user_id), after={"role": body.role},
            **ctx.audit_kwargs(reason=f"revoke {body.role}"),
        )
    return {"revoked": True, "user_id": str(body.user_id), "role": body.role}


@router.get("/{workspace_id}/members")
def list_members(
    workspace_id: UUID,
    settings: SettingsDep,
    ctx: Annotated[Any, Depends(require_permission("user.admin"))],
) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return workspaces.list_members(conn, workspace_id)


@router.get("/{workspace_id}/tasks")
def my_tasks_endpoint(workspace_id: UUID, user: CurrentUser, settings: SettingsDep) -> dict[str, Any]:
    """Unified "My Tasks" for the signed-in user in this workspace (Part 16): the verification queue
    and the Research Centre tasks they can act on, filtered by their effective permissions. Member-
    gated server-side (not merely hidden in the UI)."""
    with workspace_transaction(_engine(settings), workspace_id, user["id"]) as conn:
        if not user["is_super_admin"] and not workspaces.user_is_member(conn, user["id"], workspace_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this workspace")
        perms = permissions.effective_permissions(conn, user["id"], workspace_id, user["is_super_admin"])
        return my_tasks.my_tasks(conn, workspace_id, perms, str(user["id"]))
