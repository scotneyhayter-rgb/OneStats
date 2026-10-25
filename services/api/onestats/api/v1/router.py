"""API v1 aggregate router."""

from __future__ import annotations

from fastapi import APIRouter

from onestats.api.v1 import (
    affiliations,
    auth,
    autosync,
    batting,
    bowling,
    branding,
    competitions,
    finals_series,
    health,
    identity,
    imports,
    innings,
    match_formats,
    matches,
    onboarding,
    organisations,
    participation,
    partnerships,
    people,
    people_import,
    playing_conditions,
    premierships,
    profiles,
    relationships,
    research,
    setup,
    stats,
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
api_v1.include_router(autosync.router)
api_v1.include_router(research.router)
api_v1.include_router(finals_series.router)
api_v1.include_router(people.router)
api_v1.include_router(affiliations.router)
api_v1.include_router(identity.router)
api_v1.include_router(profiles.router)
api_v1.include_router(people_import.router)
api_v1.include_router(matches.router)
api_v1.include_router(match_formats.router)
api_v1.include_router(innings.router)
api_v1.include_router(batting.router)
api_v1.include_router(bowling.router)
api_v1.include_router(partnerships.router)
api_v1.include_router(participation.router)
api_v1.include_router(stats.router)
api_v1.include_router(premierships.router)
