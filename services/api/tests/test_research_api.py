"""Research Centre API wiring + auth gating (Phase 10, Stage 10.1; no live DB)."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from onestats.core.config import Settings
from onestats.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings(env="test", db_password=None, _env_file=None)))


def test_research_routes_registered(client):
    paths = set(client.app.openapi()["paths"].keys())
    base = "/api/v1/workspaces/{workspace_id}/research"
    for p in ("/dashboard", "/projects", "/projects/{project_id}", "/sources", "/sources/{source_id}",
              "/sources/{source_id}/file", "/sources/{source_id}/link", "/matches/{match_id}/sources",
              "/publications/{publication}/editions", "/matches/{match_id}/provenance",
              "/matches/{match_id}/conflicts", "/provenance/{claim_id}/accept", "/provenance/{claim_id}/reject",
              "/sources/{source_id}/extractions", "/sources/{source_id}/extract",
              "/sources/{source_id}/transcription", "/extractions/{extraction_id}/correct",
              "/reconstructions", "/matches/{match_id}/attach-source", "/matches/{match_id}/reconstruction",
              "/matches/{match_id}/submit-for-review", "/matches/{match_id}/verify",
              "/timeline", "/timeline/assessment", "/gaps"):
        assert f"{base}{p}" in paths, p


def test_research_requires_authentication(client):
    wid = uuid.uuid4()
    base = f"/api/v1/workspaces/{wid}/research"
    assert client.get(f"{base}/dashboard").status_code == 401
    assert client.get(f"{base}/projects").status_code == 401
    assert client.post(f"{base}/projects", json={"title": "x"}).status_code == 401
    assert client.get(f"{base}/sources").status_code == 401
    assert client.post(f"{base}/sources", json={"title": "x", "source_type": "pdf"}).status_code == 401
