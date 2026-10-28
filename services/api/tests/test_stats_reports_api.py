"""Stats report API wiring (no live DB required).

Guards a specific regression: the on-screen report endpoint (/stats/reports/{report}) and its CSV
export must expose the ``organisation_id`` (Club) query parameter. The desktop Statistics page sends
``organisation_id`` on this endpoint; when the parameter was missing from the signature FastAPI
silently dropped it, so changing the Club filter did nothing. Every report leaderboard honours the
same shared filter, so the parameter must be present wherever it can be filtered on screen.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from onestats.core.config import Settings
from onestats.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings(env="test", db_password=None, _env_file=None)))


def _get_params(client: TestClient, path: str) -> set[str]:
    spec = client.app.openapi()["paths"][path]["get"]
    return {p["name"] for p in spec.get("parameters", [])}


@pytest.mark.parametrize("path", [
    "/api/v1/workspaces/{workspace_id}/stats/reports/{report}",
    "/api/v1/workspaces/{workspace_id}/stats/reports/{report}/csv",
    "/api/v1/workspaces/{workspace_id}/stats/reports/{report}/pdf",
    "/api/v1/workspaces/{workspace_id}/stats/batting",
    "/api/v1/workspaces/{workspace_id}/stats/bowling",
])
def test_report_endpoints_expose_club_filter(client, path):
    """organisation_id (Club) must be a query parameter on every on-screen/report endpoint."""
    assert "organisation_id" in _get_params(client, path)
