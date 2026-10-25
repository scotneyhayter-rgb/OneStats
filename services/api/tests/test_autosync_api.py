"""AutoSync API wiring + auth gating (Phase 9; no live DB)."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from onestats.core.config import Settings
from onestats.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings(env="test", db_password=None, _env_file=None)))


def test_autosync_routes_registered(client):
    paths = set(client.app.openapi()["paths"].keys())
    base = "/api/v1/workspaces/{workspace_id}/autosync"
    for p in ("/connectors", "/sources", "/sync-now", "/discover-history", "/jobs", "/review",
              "/review/bulk", "/coverage", "/dashboard"):
        assert f"{base}{p}" in paths, p


def test_autosync_requires_authentication(client):
    wid = uuid.uuid4()
    base = f"/api/v1/workspaces/{wid}/autosync"
    assert client.get(f"{base}/dashboard").status_code == 401
    assert client.post(f"{base}/sync-now", json={"source_system": "x"}).status_code == 401
    assert client.get(f"{base}/review").status_code == 401
    assert client.post(f"{base}/review/{uuid.uuid4()}/accept").status_code == 401
