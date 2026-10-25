"""Match-source provenance endpoint wiring + auth gating (Phase 8, Stage 8.7; no live DB)."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from onestats.core.config import Settings
from onestats.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings(env="test", db_password=None, _env_file=None)))


def test_sources_route_registered(client):
    paths = set(client.app.openapi()["paths"].keys())
    assert "/api/v1/workspaces/{workspace_id}/matches/{match_id}/sources" in paths


def test_sources_requires_authentication(client):
    wid, mid = uuid.uuid4(), uuid.uuid4()
    assert client.get(f"/api/v1/workspaces/{wid}/matches/{mid}/sources").status_code == 401
