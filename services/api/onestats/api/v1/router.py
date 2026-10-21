"""API v1 aggregate router."""

from __future__ import annotations

from fastapi import APIRouter

from onestats.api.v1 import health

api_v1 = APIRouter()
api_v1.include_router(health.router)
