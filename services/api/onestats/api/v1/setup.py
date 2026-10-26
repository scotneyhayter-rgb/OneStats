"""First-run setup endpoints: create the initial Super Administrator (D26)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from onestats.api.deps import SettingsDep
from onestats.db.session import get_engine
from onestats.domain import auth, bootstrap

router = APIRouter(prefix="/setup", tags=["setup"])


class SetupStatus(BaseModel):
    setup_required: bool


class CreateSuperAdmin(BaseModel):
    username: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=10, max_length=256)
    setup_token: str = Field(min_length=10)


class RecoverSuperAdmin(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    new_password: str = Field(min_length=10, max_length=256)
    recovery_token: str = Field(min_length=10)


def _engine_or_503(settings):
    engine = get_engine(settings)
    if engine is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database not configured")
    return engine


@router.get("/status", response_model=SetupStatus)
def status_(settings: SettingsDep) -> SetupStatus:
    engine = _engine_or_503(settings)
    with engine.begin() as conn:
        return SetupStatus(setup_required=auth.setup_required(conn))


@router.post("/super-admin", status_code=status.HTTP_201_CREATED)
def create_super_admin(body: CreateSuperAdmin, settings: SettingsDep) -> dict:
    engine = _engine_or_503(settings)
    with engine.begin() as conn:
        try:
            bootstrap.create_super_admin(
                conn, settings, body.username, body.password, body.setup_token
            )
        except ValueError as exc:
            code = str(exc)
            http = (
                status.HTTP_409_CONFLICT
                if code == "setup_already_complete"
                else status.HTTP_400_BAD_REQUEST
            )
            raise HTTPException(http, code) from exc
    return {"created": True, "username": body.username}


@router.post("/recover-super-admin")
def recover_super_admin(body: RecoverSuperAdmin, settings: SettingsDep) -> dict:
    """Recover a Super Administrator using a one-time recovery token (generated server-side by an operator
    with host access — see docs). Requires the token file; it cannot be triggered remotely without it."""
    engine = _engine_or_503(settings)
    with engine.begin() as conn:
        try:
            bootstrap.recover_super_admin(conn, settings, body.recovery_token, body.username, body.new_password)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"recovered": True, "username": body.username}
