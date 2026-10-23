"""Venue & team API wiring + authorisation-gating tests (no live DB required).

Confirms the routes are registered and that every endpoint is behind authentication. Full
behavioural coverage lives in ``test_venues_teams.py`` against a live database.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from onestats.core.config import Settings
from onestats.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings(env="test", db_password=None, _env_file=None)))


def _paths(client: TestClient) -> set[str]:
    return set(client.app.openapi()["paths"].keys())


def test_venue_and_team_routes_registered(client):
    paths = _paths(client)
    vbase = "/api/v1/workspaces/{workspace_id}/venues"
    tbase = "/api/v1/workspaces/{workspace_id}/teams"
    for base in (vbase, tbase):
        assert base in paths
        assert f"{base}/{{venue_id}}" in paths or f"{base}/{{team_id}}" in paths
        assert f"{base}/merge" in paths
        assert f"{base}/assert-distinct" in paths


def test_venue_endpoints_require_authentication(client):
    wid = uuid.uuid4()
    base = f"/api/v1/workspaces/{wid}/venues"
    assert client.get(base).status_code == 401
    assert client.post(base, json={"name": "X"}).status_code == 401
    assert client.get(f"{base}/{uuid.uuid4()}").status_code == 401
    assert client.post(f"{base}/merge", json={
        "canonical_venue_id": str(uuid.uuid4()), "merged_venue_id": str(uuid.uuid4()),
    }).status_code == 401


def test_team_endpoints_require_authentication(client):
    wid = uuid.uuid4()
    base = f"/api/v1/workspaces/{wid}/teams"
    assert client.get(base).status_code == 401
    assert client.post(base, json={"organisation_id": str(uuid.uuid4()), "name": "X"}).status_code == 401
    assert client.get(f"{base}/{uuid.uuid4()}").status_code == 401
    assert client.post(f"{base}/merge", json={
        "canonical_team_id": str(uuid.uuid4()), "merged_team_id": str(uuid.uuid4()),
    }).status_code == 401
