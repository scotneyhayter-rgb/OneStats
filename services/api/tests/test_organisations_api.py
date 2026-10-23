"""Organisation API wiring + authorisation-gating tests (no live DB required).

Confirms the routes are registered and that every organisation endpoint is behind
authentication — an unauthenticated caller is rejected before any workspace work. Full
behavioural coverage (merge safety, isolation, audit) lives in ``test_organisations.py``
against a live database.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from onestats.core.config import Settings
from onestats.main import create_app


@pytest.fixture
def client() -> TestClient:
    # No DB password → database reported as not configured; auth still gates first.
    return TestClient(create_app(Settings(env="test", db_password=None, _env_file=None)))


def _paths(client: TestClient) -> set[str]:
    return set(client.app.openapi()["paths"].keys())


def test_organisation_routes_are_registered(client):
    paths = _paths(client)
    base = "/api/v1/workspaces/{workspace_id}/organisations"
    assert base in paths
    assert f"{base}/{{organisation_id}}" in paths
    assert f"{base}/merge" in paths
    assert f"{base}/assert-distinct" in paths
    assert f"{base}/{{organisation_id}}/duplicate-candidates" in paths


def test_endpoints_require_authentication(client):
    wid = uuid.uuid4()
    base = f"/api/v1/workspaces/{wid}/organisations"
    # No bearer token → 401, regardless of DB availability.
    assert client.get(base).status_code == 401
    assert client.post(base, json={"name": "X"}).status_code == 401
    assert client.post(f"{base}/merge", json={
        "canonical_organisation_id": str(uuid.uuid4()),
        "merged_organisation_id": str(uuid.uuid4()),
    }).status_code == 401
    assert client.get(f"{base}/{uuid.uuid4()}").status_code == 401
