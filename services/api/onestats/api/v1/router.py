"""API v1 aggregate router."""

from __future__ import annotations

from fastapi import APIRouter

from onestats.api.v1 import auth, branding, health, onboarding, setup, workspaces

api_v1 = APIRouter()
api_v1.include_router(health.router)
api_v1.include_router(auth.router)
api_v1.include_router(setup.router)
api_v1.include_router(workspaces.router)
api_v1.include_router(onboarding.router)
api_v1.include_router(branding.router)
