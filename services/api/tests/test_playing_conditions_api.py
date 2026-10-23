"""Playing-conditions API wiring + authorisation-gating tests (no live DB required)."""

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


def test_playing_condition_routes_registered(client):
    paths = _paths(client)
    base = "/api/v1/workspaces/{workspace_id}/playing-conditions"
    assert base in paths
    assert f"{base}/resolve" in paths
    assert f"{base}/{{scope}}/{{target_id}}" in paths


def test_playing_condition_endpoints_require_authentication(client):
    wid = uuid.uuid4()
    base = f"/api/v1/workspaces/{wid}/playing-conditions"
    assert client.get(base).status_code == 401
    assert client.put(base, json={"scope": "competition", "target_id": str(uuid.uuid4())}).status_code == 401
    assert client.get(f"{base}/resolve", params={"competition_id": str(uuid.uuid4())}).status_code == 401
    assert client.get(f"{base}/competition/{uuid.uuid4()}").status_code == 401
