"""Shared API dependencies: session authentication and authorisation."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, status

from onestats.core.config import Settings, get_settings
from onestats.db.session import get_engine
from onestats.domain import auth

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
