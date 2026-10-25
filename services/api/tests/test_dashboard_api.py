"""Dashboard API wiring + auth gating (no live DB)."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from onestats.core.config import Settings
from onestats.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings(env="test", db_password=None, _env_file=None)))


def test_dashboard_route_registered(client):
    paths = set(client.app.openapi()["paths"].keys())
    assert "/api/v1/workspaces/{workspace_id}/dashboard" in paths


def test_dashboard_requires_authentication(client):
    wid = uuid.uuid4()
    assert client.get(f"/api/v1/workspaces/{wid}/dashboard").status_code == 401
