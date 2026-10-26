"""Workspace API & Integrations management endpoints (workspace-scoped, admin-gated).

Clubs/associations manage their own external-provider credentials here — no config-file or source edits.
Gated by ``import.configure`` ("Configure import connectors"), which is held by workspace admins and super
admins. Credentials are workspace-isolated (RLS + the workspace transaction), secrets are encrypted at rest
and **never returned** by any endpoint (only masked status), and every action is audited. Connectivity is
proven only by the Test endpoint (a real authenticated request), never assumed.
"""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import integrations

router = APIRouter(prefix="/workspaces/{workspace_id}/integrations", tags=["integrations"])

# "Configure import connectors" — workspace-admin / super-admin only (backend-enforced RBAC).
ManageCtx = Annotated[RequestContext, Depends(require_permission("import.configure"))]

_ERRORS = {
    "unknown_provider": status.HTTP_400_BAD_REQUEST,
    "credential_not_found": status.HTTP_404_NOT_FOUND,
    "url_scheme_not_allowed": status.HTTP_400_BAD_REQUEST,
    "url_must_not_contain_credentials": status.HTTP_400_BAD_REQUEST,
    "url_missing_host": status.HTTP_400_BAD_REQUEST,
    "url_host_unresolvable": status.HTTP_400_BAD_REQUEST,
    "url_resolves_to_internal_address": status.HTTP_400_BAD_REQUEST,
    "invalid_url": status.HTTP_400_BAD_REQUEST,
}


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


def _err(exc: ValueError) -> HTTPException:
    key = str(exc).split(":", 1)[0]
    return HTTPException(_ERRORS.get(key, status.HTTP_400_BAD_REQUEST), str(exc))


class CreateCredential(BaseModel):
    provider: str = Field(min_length=1, max_length=50)
    label: str = Field(default="", max_length=100)
    # secret fields (e.g. {"api_key": "..."}) — encrypted at rest, never returned
    secrets: dict[str, str] = Field(default_factory=dict)
    # non-secret config (e.g. {"org_id": "...", "tenant": "ca"})
    config: dict[str, Any] = Field(default_factory=dict)


class RotateCredential(BaseModel):
    secrets: dict[str, str] = Field(min_length=1)


class EnabledBody(BaseModel):
    enabled: bool


@router.get("/providers")
def list_providers(workspace_id: UUID, settings: SettingsDep, ctx: ManageCtx) -> list[dict[str, Any]]:
    """The supported integrations and their config schemas (secret vs non-secret fields)."""
    return integrations.providers()


@router.get("/credentials")
def list_credentials(workspace_id: UUID, settings: SettingsDep, ctx: ManageCtx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return integrations.list_credentials(conn, workspace_id)


@router.post("/credentials", status_code=status.HTTP_201_CREATED)
def create_credential(workspace_id: UUID, body: CreateCredential, settings: SettingsDep,
                      ctx: ManageCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return integrations.create_credential(conn, settings, workspace_id, str(ctx.user["id"]),
                                                  provider=body.provider, secrets=body.secrets,
                                                  config=body.config, label=body.label)
        except ValueError as exc:
            raise _err(exc) from exc


@router.post("/credentials/{cred_id}/rotate")
def rotate_credential(workspace_id: UUID, cred_id: UUID, body: RotateCredential, settings: SettingsDep,
                      ctx: ManageCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return integrations.rotate_credential(conn, settings, workspace_id, str(ctx.user["id"]),
                                                  cred_id, secrets=body.secrets)
        except ValueError as exc:
            raise _err(exc) from exc


@router.patch("/credentials/{cred_id}")
def set_enabled(workspace_id: UUID, cred_id: UUID, body: EnabledBody, settings: SettingsDep,
                ctx: ManageCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return integrations.set_enabled(conn, workspace_id, str(ctx.user["id"]), cred_id, body.enabled)
        except ValueError as exc:
            raise _err(exc) from exc


@router.post("/credentials/{cred_id}/revoke")
def revoke_credential(workspace_id: UUID, cred_id: UUID, settings: SettingsDep,
                      ctx: ManageCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return integrations.revoke_credential(conn, workspace_id, str(ctx.user["id"]), cred_id)
        except ValueError as exc:
            raise _err(exc) from exc


@router.post("/credentials/{cred_id}/test")
def test_credential(workspace_id: UUID, cred_id: UUID, settings: SettingsDep, ctx: ManageCtx) -> dict[str, Any]:
    """Attempt a real authenticated request with the stored credential; records + returns the result."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        try:
            return integrations.test_connectivity(conn, settings, workspace_id, str(ctx.user["id"]), cred_id)
        except ValueError as exc:
            raise _err(exc) from exc


@router.get("/audit")
def integration_audit(workspace_id: UUID, settings: SettingsDep, ctx: ManageCtx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return integrations.integration_audit(conn, workspace_id)
