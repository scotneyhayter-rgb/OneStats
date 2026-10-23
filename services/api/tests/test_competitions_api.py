"""Competition API wiring + authorisation-gating tests (no live DB required)."""

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


def test_competition_routes_registered(client):
    paths = _paths(client)
    base = "/api/v1/workspaces/{workspace_id}/competitions"
    assert base in paths
    assert f"{base}/{{competition_id}}" in paths
    assert f"{base}/entries" in paths
    assert f"{base}/classifications" in paths
    assert f"{base}/classifications/unresolved" in paths
    assert f"{base}/{{competition_id}}/grades" in paths
    assert f"{base}/{{competition_id}}/seasons" in paths


def test_competition_endpoints_require_authentication(client):
    wid = uuid.uuid4()
    base = f"/api/v1/workspaces/{wid}/competitions"
    assert client.get(base).status_code == 401
    assert client.post(base, json={"name": "X"}).status_code == 401
    assert client.get(f"{base}/{uuid.uuid4()}").status_code == 401
    assert client.post(f"{base}/entries", json={
        "team_id": str(uuid.uuid4()), "grade_id": str(uuid.uuid4()), "season_id": str(uuid.uuid4()),
    }).status_code == 401
    assert client.get(f"{base}/classifications").status_code == 401
