"""People API wiring + authorisation-gating tests (no live DB required)."""

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


def test_people_routes_registered(client):
    paths = _paths(client)
    base = "/api/v1/workspaces/{workspace_id}/people"
    assert base in paths
    assert f"{base}/{{person_id}}" in paths
    assert f"{base}/{{person_id}}/names" in paths
    assert f"{base}/{{person_id}}/roles" in paths
    assert f"{base}/{{person_id}}/duplicate-candidates" in paths


def test_people_endpoints_require_authentication(client):
    wid = uuid.uuid4()
    base = f"/api/v1/workspaces/{wid}/people"
    assert client.get(base).status_code == 401
    assert client.post(base, json={"display_name": "X"}).status_code == 401
    assert client.get(f"{base}/{uuid.uuid4()}").status_code == 401
    assert client.post(f"{base}/{uuid.uuid4()}/roles", json={"role": "player"}).status_code == 401
