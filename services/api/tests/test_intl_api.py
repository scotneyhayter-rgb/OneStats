"""Smoke tests for the match-index and scheduler routers — auth gating and registration.

The domain logic is covered by test_match_index / test_scheduler_tasks; here we confirm the HTTP
surface exists and is gated (no token -> 401), which needs no database.
"""
from __future__ import annotations

WS = "00000000-0000-0000-0000-0000000000aa"


def test_match_index_requires_auth(client):
    for path in (f"/api/v1/workspaces/{WS}/match-index",
                 f"/api/v1/workspaces/{WS}/match-index/summary"):
        assert client.get(path).status_code == 401
    assert client.post(f"/api/v1/workspaces/{WS}/match-index/register",
                       json={"format": "test", "source_refs": {"x": "1"}}).status_code == 401


def test_scheduler_requires_auth(client):
    assert client.get(f"/api/v1/workspaces/{WS}/scheduler/tasks").status_code == 401
    assert client.post(f"/api/v1/workspaces/{WS}/scheduler/tasks/{WS}/run-now").status_code == 401


def test_intl_stats_requires_auth(client):
    assert client.get(f"/api/v1/workspaces/{WS}/intl-stats/career/{WS}").status_code == 401
    assert client.get(f"/api/v1/workspaces/{WS}/intl-stats/leaders/test/batting").status_code == 401


def test_routes_are_registered(client):
    paths = client.app.openapi()["paths"]
    assert f"/api/v1/workspaces/{{workspace_id}}/match-index/summary" in paths
    assert f"/api/v1/workspaces/{{workspace_id}}/scheduler/tasks/{{task_id}}/run-now" in paths
    assert f"/api/v1/workspaces/{{workspace_id}}/intl-stats/career/{{person_id}}" in paths
    assert f"/api/v1/workspaces/{{workspace_id}}/intl-stats/leaders/{{fmt}}/{{discipline}}" in paths
