"""Authentication endpoints (login / logout / me)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from onestats.api.deps import BearerToken, CurrentUser, SettingsDep
from onestats.core import security
from onestats.db.session import get_engine
from onestats.domain import auth

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class UserInfo(BaseModel):
    id: str
    username: str
    display_name: str | None = None
    is_super_admin: bool
    must_change_password: bool = False


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
def login(body: LoginRequest, settings: SettingsDep, request: Request) -> LoginResponse:
    engine = _engine_or_503(settings)
    ip = request.client.host if request.client else None
    with engine.begin() as conn:
        if auth.is_rate_limited(conn, body.username):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                "Too many failed sign-in attempts. Please wait and try again.")
        user = auth.authenticate(conn, body.username, body.password)
        auth.record_attempt(conn, body.username, user["id"] if user else None, ip, bool(user))
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
            must_change_password=bool(user.get("must_change_password")),
        ),
    )


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: ChangePasswordRequest, user: CurrentUser, settings: SettingsDep) -> Response:
    """Change the signed-in user's own password (used for the first-login forced change)."""
    err = security.password_strength_error(body.new_password)
    if err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, err)
    engine = _engine_or_503(settings)
    with engine.begin() as conn:
        if not auth.verify_current_password(conn, user["id"], body.current_password):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
        auth.change_password(conn, user["id"], body.new_password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
        must_change_password=bool(user.get("must_change_password")),
    )
