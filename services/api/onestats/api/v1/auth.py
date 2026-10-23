"""Authentication endpoints (login / logout / me)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from onestats.api.deps import BearerToken, CurrentUser, SettingsDep
from onestats.db.session import get_engine
from onestats.domain import auth

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=256)


class UserInfo(BaseModel):
    id: str
    username: str
    display_name: str | None = None
    is_super_admin: bool


class LoginResponse(BaseModel):
    token: str
    expires_at: datetime
    user: UserInfo


def _engine_or_503(settings):
    engine = get_engine(settings)
    if engine is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return engine


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, settings: SettingsDep) -> LoginResponse:
    engine = _engine_or_503(settings)
    with engine.begin() as conn:
        user = auth.authenticate(conn, body.username, body.password)
        if not user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
        token, expires = auth.create_session(conn, user["id"], settings.session_ttl_hours)
    return LoginResponse(
        token=token,
        expires_at=expires,
        user=UserInfo(
            id=str(user["id"]),
            username=user["username"],
            display_name=user.get("display_name"),
            is_super_admin=user["is_super_admin"],
        ),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(token: BearerToken, settings: SettingsDep) -> Response:
    if token:
        engine = get_engine(settings)
        if engine is not None:
            with engine.begin() as conn:
                auth.revoke_session(conn, token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserInfo)
def me(user: CurrentUser) -> UserInfo:
    return UserInfo(
        id=str(user["id"]),
        username=user["username"],
        display_name=user.get("display_name"),
        is_super_admin=user["is_super_admin"],
    )
