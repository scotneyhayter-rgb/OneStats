"""Organisation-relationship API wiring + authorisation-gating tests (no live DB required)."""

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


def test_relationship_routes_registered(client):
    paths = _paths(client)
    base = "/api/v1/workspaces/{workspace_id}/organisation-relationships"
    assert base in paths
    assert f"{base}/timeline" in paths
    assert f"{base}/affiliation" in paths
    assert f"{base}/{{relationship_id}}/void" in paths
    assert f"{base}/{{relationship_id}}/restore" in paths


def test_relationship_endpoints_require_authentication(client):
    wid = uuid.uuid4()
    base = f"/api/v1/workspaces/{wid}/organisation-relationships"
    assert client.post(base, json={
        "from_org_id": str(uuid.uuid4()), "to_org_id": str(uuid.uuid4()), "rel_type": "affiliation",
    }).status_code == 401
    assert client.get(base, params={"organisation_id": str(uuid.uuid4())}).status_code == 401
    assert client.get(f"{base}/timeline", params={"organisation_id": str(uuid.uuid4())}).status_code == 401
    assert client.post(f"{base}/{uuid.uuid4()}/void").status_code == 401
