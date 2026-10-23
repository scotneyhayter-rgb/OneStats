"""Identity-resolution API wiring + authorisation-gating tests (no live DB required)."""

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


def test_identity_routes_registered(client):
    paths = _paths(client)
    base = "/api/v1/workspaces/{workspace_id}/identity"
    assert f"{base}/candidates" in paths
    assert f"{base}/compare" in paths
    assert f"{base}/merge" in paths
    assert f"{base}/merges/{{merge_id}}/undo" in paths
    assert f"{base}/assert-distinct" in paths
    assert f"{base}/reviews" in paths
    assert f"{base}/reviews/{{review_id}}/decide" in paths


def test_identity_endpoints_require_authentication(client):
    wid = uuid.uuid4()
    base = f"/api/v1/workspaces/{wid}/identity"
    assert client.get(f"{base}/candidates", params={"person_id": str(uuid.uuid4())}).status_code == 401
    assert client.post(f"{base}/merge", json={
        "canonical_person_id": str(uuid.uuid4()), "merged_person_id": str(uuid.uuid4()),
    }).status_code == 401
    assert client.post(f"{base}/assert-distinct", json={
        "person_a_id": str(uuid.uuid4()), "person_b_id": str(uuid.uuid4()),
    }).status_code == 401
    assert client.get(f"{base}/reviews").status_code == 401
