"""Guided onboarding endpoints (Super-Admin): start / resume / save / activate."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from onestats.api.deps import SettingsDep, require_super_admin
from onestats.db.session import get_engine
from onestats.domain import onboarding

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

SuperAdmin = Annotated[dict, Depends(require_super_admin)]


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


class StartDraft(BaseModel):
    template: str | None = Field(default=None, max_length=40)


class SaveDraft(BaseModel):
    state: dict[str, Any] = Field(default_factory=dict)
    current_step: int | None = Field(default=None, ge=1, le=20)


@router.post("", status_code=status.HTTP_201_CREATED)
def start(body: StartDraft, admin: SuperAdmin, settings: SettingsDep) -> dict[str, Any]:
    with _engine(settings).begin() as conn:
        draft_id = onboarding.start_draft(conn, admin["id"], body.template)
        return onboarding.get_draft(conn, draft_id)


@router.get("/{draft_id}")
def get(draft_id: UUID, admin: SuperAdmin, settings: SettingsDep) -> dict[str, Any]:
    with _engine(settings).begin() as conn:
        draft = onboarding.get_draft(conn, draft_id, requester_id=admin["id"])
    if draft is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "draft_not_found")
    return draft


@router.patch("/{draft_id}")
def save(draft_id: UUID, body: SaveDraft, admin: SuperAdmin, settings: SettingsDep) -> dict[str, Any]:
    with _engine(settings).begin() as conn:
        try:
            return onboarding.save_draft(conn, draft_id, body.state, body.current_step,
                                         requester_id=admin["id"])
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/{draft_id}/activate", status_code=status.HTTP_201_CREATED)
def activate(draft_id: UUID, admin: SuperAdmin, settings: SettingsDep) -> dict[str, Any]:
    with _engine(settings).begin() as conn:
        try:
            ws_id = onboarding.activate_draft(conn, draft_id, admin["id"])
        except ValueError as exc:
            code = str(exc)
            http = (
                status.HTTP_409_CONFLICT
                if code in ("duplicate_identifier", "draft_not_active")
                else status.HTTP_400_BAD_REQUEST
            )
            raise HTTPException(http, code) from exc
        return {"activated": True, "workspace_id": str(ws_id)}
