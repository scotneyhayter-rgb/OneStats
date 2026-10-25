"""Ask OneStats endpoint (Phase 14, deliverable 28).

Natural-language question in → deterministic report answer out. Permission- and workspace-scoped (the
answer's numbers come from the one engine on approved data only). The NL layer never fabricates: an
unmapped question returns the nearest supported reports.
"""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from onestats.api.deps import RequestContext, SettingsDep, require_permission
from onestats.db.session import get_engine
from onestats.db.workspace import workspace_transaction
from onestats.domain import ask as ask_domain

router = APIRouter(prefix="/workspaces/{workspace_id}/ask", tags=["ask"])

ViewCtx = Annotated[RequestContext, Depends(require_permission("match.view"))]


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=400)
    top: int = Field(default=10, ge=1, le=50)


@router.post("")
def ask(workspace_id: UUID, body: AskBody, settings: SettingsDep, ctx: ViewCtx) -> dict[str, Any]:
    with workspace_transaction(_engine(settings), workspace_id) as conn:
        return ask_domain.answer(conn, workspace_id, body.question, top=body.top)
