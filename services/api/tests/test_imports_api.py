"""Import API wiring + authorisation-gating tests (no live DB required)."""

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


def test_import_routes_registered(client):
    paths = _paths(client)
    base = "/api/v1/workspaces/{workspace_id}/imports"
    assert base in paths
    assert f"{base}/{{batch_id}}" in paths
    assert f"{base}/{{batch_id}}/validate" in paths
    assert f"{base}/{{batch_id}}/promote" in paths
    assert f"{base}/{{batch_id}}/cancel" in paths
    assert f"{base}/{{batch_id}}/rollback" in paths
    # Phase 8 universal import (any format)
    assert f"{base}/detect" in paths
    assert f"{base}/generic" in paths


def test_import_endpoints_require_authentication(client):
    wid = uuid.uuid4()
    base = f"/api/v1/workspaces/{wid}/imports"
    assert client.get(base).status_code == 401
    assert client.post(base, json={"data": {"clubs": []}}).status_code == 401
    assert client.post(f"{base}/{uuid.uuid4()}/promote").status_code == 401
    assert client.post(f"{base}/{uuid.uuid4()}/rollback").status_code == 401
    assert client.post(f"{base}/detect", json={"content": "x"}).status_code == 401
    assert client.post(f"{base}/generic", json={"content": "x"}).status_code == 401
