"""Finals Series API wiring + authorisation-gating tests (no live DB required)."""

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


def test_finals_series_routes_registered(client):
    paths = _paths(client)
    base = "/api/v1/workspaces/{workspace_id}/finals-series"
    assert base in paths
    assert f"{base}/{{series_id}}" in paths
    assert f"{base}/{{series_id}}/teams" in paths
    assert f"{base}/{{series_id}}/games" in paths
    assert f"{base}/{{series_id}}/outcome" in paths


def test_finals_series_endpoints_require_authentication(client):
    wid = uuid.uuid4()
    base = f"/api/v1/workspaces/{wid}/finals-series"
    assert client.get(base).status_code == 401
    assert client.post(base, json={"competition_id": str(uuid.uuid4()), "name": "S"}).status_code == 401
    assert client.post(f"{base}/{uuid.uuid4()}/games", json={"game_number": 1}).status_code == 401
