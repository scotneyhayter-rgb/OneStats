"""Media Archive API wiring + auth gating (Phase 11; no live DB)."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from onestats.core.config import Settings
from onestats.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings(env="test", db_password=None, _env_file=None)))


def test_media_routes_registered(client):
    paths = set(client.app.openapi()["paths"].keys())
    base = "/api/v1/workspaces/{workspace_id}/media"
    for p in ("/providers", "/assets", "/assets/external", "/assets/{asset_id}", "/assets/{asset_id}/file",
              "/assets/{asset_id}/thumbnail", "/assets/{asset_id}/link",
              "/entities/{entity_type}/{entity_id}/assets"):
        assert f"{base}{p}" in paths, p


def test_media_requires_authentication(client):
    wid = uuid.uuid4()
    base = f"/api/v1/workspaces/{wid}/media"
    assert client.get(f"{base}/providers").status_code == 401
    assert client.get(f"{base}/assets").status_code == 401
    assert client.post(f"{base}/assets/external", json={"url": "x"}).status_code == 401
