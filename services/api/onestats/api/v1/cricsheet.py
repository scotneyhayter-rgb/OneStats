"""Cricsheet import management endpoints (Parts F/G) — backs the Import Management UI.

Reads (import progress, imported matches, errors, source info, identity reviews) require ``match.view``;
backfill controls (start/pause/resume/cancel) require ``import.manage``. All figures are genuine (from
the import log and backfill state); nothing here downloads synchronously — the background worker performs
downloads, so controls only set state. Workspace-scoped (FORCE RLS) and audited by the domain layer.
"""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import person_resolution
from onestats.domain.intl import cricsheet_backfill as backfill
from onestats.domain.intl import cricsheet_download as dl

router = APIRouter(prefix="/workspaces/{workspace_id}/cricsheet", tags=["cricsheet"])

ViewCtx = Annotated[RequestContext, Depends(require_permission("match.view"))]
ManageCtx = Annotated[RequestContext, Depends(require_permission("import.manage"))]

_ACTIONS = ("start", "pause", "resume", "cancel")


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


@router.get("/summary")
def summary(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx) -> dict[str, Any]:
    """Import counts + per-format backfill state for the dashboard."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return {"imports": dl.summary(conn, workspace_id),
                "backfills": backfill.list_all(conn, workspace_id)}


@router.get("/imports")
def imports(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx,
            status_filter: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    """The import log — View Imported Matches / Resolve Import Errors (status_filter=failed) /
    Review Imported Scorecards (status_filter=awaiting_verification)."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return dl.list_imports(conn, workspace_id, status=status_filter, limit=limit)


@router.get("/backfills")
def backfills(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx) -> list[dict[str, Any]]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return backfill.list_all(conn, workspace_id)


@router.post("/backfills/{fmt}/{action}")
def control_backfill(workspace_id: UUID, fmt: str, action: str, settings: SettingsDep,
                     ctx: ManageCtx) -> dict[str, Any]:
    """Start / pause / resume / cancel the historical backfill for a format. The worker performs the
    actual downloads; this only sets state."""
    if action not in _ACTIONS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown action")
    actor = str(ctx.user["id"])
    try:
        with workspace_transaction(_engine(settings), workspace_id) as conn:
            if action == "start":
                return backfill.start(conn, workspace_id, actor, fmt)
            return backfill.set_status(conn, workspace_id, actor, fmt, action)
    except ValueError as exc:
        code = status.HTTP_404_NOT_FOUND if str(exc) in ("invalid_format", "backfill_not_found") \
            else status.HTTP_400_BAD_REQUEST
        raise HTTPException(code, str(exc))


@router.get("/identity-reviews")
def identity_reviews(workspace_id: UUID, settings: SettingsDep, ctx: ViewCtx,
                     status_filter: str = "pending") -> list[dict[str, Any]]:
    """Player identities awaiting resolution (ambiguous same-name imports) — Resolve Player Identities."""
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return person_resolution.list_reviews(conn, status=status_filter)
