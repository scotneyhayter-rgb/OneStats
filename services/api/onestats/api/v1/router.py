"""API v1 aggregate router."""

from __future__ import annotations

from fastapi import APIRouter

from onestats.api.v1 import (
    affiliations,
    auth,
    branding,
    competitions,
    finals_series,
    health,
    identity,
    imports,
    onboarding,
    organisations,
    people,
    playing_conditions,
    relationships,
    setup,
    teams,
    venues,
    workspaces,
)

api_v1 = APIRouter()
api_v1.include_router(health.router)
api_v1.include_router(auth.router)
api_v1.include_router(setup.router)
api_v1.include_router(workspaces.router)
api_v1.include_router(onboarding.router)
api_v1.include_router(branding.router)
api_v1.include_router(organisations.router)
api_v1.include_router(venues.router)
api_v1.include_router(teams.router)
api_v1.include_router(competitions.router)
api_v1.include_router(playing_conditions.router)
api_v1.include_router(relationships.router)
api_v1.include_router(imports.router)
api_v1.include_router(finals_series.router)
api_v1.include_router(people.router)
api_v1.include_router(affiliations.router)
api_v1.include_router(identity.router)
