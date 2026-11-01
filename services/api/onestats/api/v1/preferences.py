"""Current-user preferences API (Part 15) — dashboard customisation and similar per-user settings.

Scoped to the authenticated user: the user_preference RLS policy (keyed on the user context) means
a user can only read/write their own preferences. A namespace groups a set of preferences (e.g.
"dashboard"); an optional workspace makes them per-workspace. Any authenticated user may use this —
preferences are a convenience layer and never affect permissions.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from onestats.api.deps import CurrentUser, SettingsDep
from onestats.db.session import get_engine
from onestats.db.workspace import user_transaction
from onestats.domain import preferences

router = APIRouter(prefix="/me/preferences", tags=["preferences"])

_NS = r"^[a-z][a-z0-9_]{0,40}$"


def _engine(settings):
    eng = get_engine(settings)
    if eng is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return eng


class PrefsBody(BaseModel):
    workspace_id: UUID | None = None
    prefs: dict[str, Any] = Field(default_factory=dict)


@router.get("/{namespace}")
def get_prefs(namespace: str, user: CurrentUser, settings: SettingsDep,
              workspace_id: UUID | None = None) -> dict[str, Any]:
    if not _valid_ns(namespace):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_namespace")
    with user_transaction(_engine(settings), user["id"]) as conn:
        return {"namespace": namespace, "workspace_id": str(workspace_id) if workspace_id else None,
                "prefs": preferences.get_preferences(conn, user["id"], namespace, workspace_id)}


@router.put("/{namespace}")
def put_prefs(namespace: str, body: PrefsBody, user: CurrentUser, settings: SettingsDep) -> dict[str, Any]:
    if not _valid_ns(namespace):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_namespace")
    with user_transaction(_engine(settings), user["id"]) as conn:
        prefs = preferences.set_preferences(conn, user["id"], namespace, body.prefs, body.workspace_id)
    return {"namespace": namespace, "workspace_id": str(body.workspace_id) if body.workspace_id else None,
            "prefs": prefs}


def _valid_ns(ns: str) -> bool:
    import re
    return bool(re.match(_NS, ns))
