"""Profile API wiring + authorisation-gating tests (no live DB required)."""

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


def test_profile_routes_registered(client):
    paths = _paths(client)
    base = "/api/v1/workspaces/{workspace_id}/people"
    assert f"{base}/{{person_id}}/profile" in paths
    assert f"{base}/{{person_id}}/public-profile" in paths
    assert f"{base}/{{person_id}}/numbers" in paths
    assert f"{base}/{{person_id}}/leadership" in paths
    assert f"{base}/{{person_id}}/recognition" in paths
    assert f"{base}/{{person_id}}/photos" in paths
    assert f"{base}/photos/{{photo_id}}/file" in paths


def test_profile_endpoints_require_authentication(client):
    wid = uuid.uuid4()
    pid = uuid.uuid4()
    base = f"/api/v1/workspaces/{wid}/people"
    assert client.get(f"{base}/{pid}/profile").status_code == 401
    assert client.put(f"{base}/{pid}/profile", json={"biography": "x"}).status_code == 401
    assert client.post(f"{base}/{pid}/recognition", json={"recognition_type": "life_member"}).status_code == 401
    assert client.get(f"{base}/photos/{uuid.uuid4()}/file").status_code == 401
